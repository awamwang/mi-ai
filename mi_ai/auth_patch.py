"""运行时修补 miservice / xiaogpt：失败不删 passToken，统一 token 路径。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mi_ai.paths import get_token_path
from mi_ai.token_store import SafeMiTokenStore, extract_durable

_LOGGER = logging.getLogger(__package__)
_PATCHED = False


def apply_auth_patches() -> None:
    """幂等：替换 MiTokenStore，并加固 MiAccount.login / mi_request。"""
    global _PATCHED
    if _PATCHED:
        return

    import miservice.miaccount as ma
    from miservice.miaccount import MiAccount, get_random

    ma.MiTokenStore = SafeMiTokenStore  # type: ignore[misc, assignment]

    _orig_init = MiAccount.__init__

    def _patched_init(self, session, username, password, token_store=None):
        if isinstance(token_store, (str, Path)):
            token_store = SafeMiTokenStore(token_store)
        elif token_store is None:
            token_store = SafeMiTokenStore(get_token_path())
        _orig_init(self, session, username, password, token_store)

    async def _patched_login(self, sid):
        """相对上游：保留已有 passToken；响应缺字段时不 KeyError。"""
        durable_before = extract_durable(self.token)
        if not self.token:
            self.token = {"deviceId": get_random(16).upper()}
        elif "deviceId" not in self.token:
            self.token["deviceId"] = get_random(16).upper()

        try:
            resp = await self._serviceLogin(f"serviceLogin?sid={sid}&_json=true")
            if resp.get("code") != 0:
                data = {
                    "_json": "true",
                    "qs": resp["qs"],
                    "sid": resp["sid"],
                    "_sign": resp["_sign"],
                    "callback": resp["callback"],
                    "user": self.username,
                    "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
                }
                resp = await self._serviceLogin("serviceLoginAuth2", data)
                if resp.get("code") != 0:
                    raise Exception(resp)

            if "userId" in resp:
                self.token["userId"] = resp["userId"]
            if "passToken" in resp:
                self.token["passToken"] = resp["passToken"]

            # 已有 passToken 时，续期响应可能不再回传 passToken
            if "passToken" not in self.token or "userId" not in self.token:
                raise Exception(
                    {
                        "code": resp.get("code"),
                        "desc": "响应缺少 userId/passToken，且本地无可用长期凭证",
                        "notificationUrl": resp.get("notificationUrl"),
                        "securityStatus": resp.get("securityStatus"),
                    }
                )

            # securityStatus=16 等：需要短信/身份验证，location 常为空
            location = (resp.get("location") or "").strip()
            if not location or resp.get("securityStatus") == 16:
                raise Exception(resp)

            nonce = resp.get("nonce")
            ssecurity = resp.get("ssecurity") or resp.get("psecurity")
            if nonce is None:
                query = parse_qs(urlparse(location).query)
                if query.get("nonce"):
                    nonce = query["nonce"][0]
            if nonce is None or not ssecurity:
                raise Exception(resp)

            service_token = await self._securityTokenService(
                location, nonce, ssecurity
            )
            self.token[sid] = (ssecurity, service_token)
            if self.token_store:
                self.token_store.save_token(self.token)
            return True

        except Exception as e:
            detail = str(e)
            # 身份验证类失败较常见，降为 warning 避免刷屏
            if "securityStatus" in detail or "notificationUrl" in detail:
                _LOGGER.warning("login(%s) 需要验证或未完成：%s", sid, detail[:240])
            else:
                _LOGGER.exception("Exception on login %s: %s", self.username, e)
            durable = extract_durable(self.token) or durable_before
            if durable.get("passToken"):
                self.token = dict(durable)
                if self.token_store:
                    self.token_store.save_token(self.token)
                _LOGGER.warning("login(%s) 失败，已保留 passToken", sid)
            else:
                self.token = None
                if self.token_store:
                    self.token_store.save_token()
            return False

    async def _patched_mi_request(self, sid, url, data, headers, relogin=True):
        headers = dict(headers)
        headers["User-Agent"] = self.now_ua
        if (self.token and sid in self.token) or await self.login(sid):
            cookies = {
                "userId": self.token["userId"],
                "serviceToken": self.token[sid][1],
            }
            content = data(self.token, cookies) if callable(data) else data
            method = "GET" if data is None else "POST"
            _LOGGER.info("%s %s", url, content)
            async with self.session.request(
                method, url, data=content, cookies=cookies, headers=headers
            ) as r:
                status = r.status
                if status == 200:
                    resp = await r.json(content_type=None)
                    code = resp["code"]
                    if code == 0:
                        return resp
                    if "auth" in resp.get("message", "").lower():
                        status = 401
                else:
                    resp = await r.text()
            if status == 401 and relogin:
                _LOGGER.warning("Auth error on request %s，保留 passToken 后重登", url)
                durable = extract_durable(self.token)
                self.token = dict(durable) if durable else {"deviceId": get_random(16).upper()}
                if sid in self.token:
                    del self.token[sid]
                if self.token_store:
                    self.token_store.save_token(self.token)
                return await self.mi_request(sid, url, data, headers, False)
        else:
            resp = "Login failed"
        raise Exception(f"Error {url}: {resp}")

    MiAccount.__init__ = _patched_init  # type: ignore[method-assign]
    MiAccount.login = _patched_login  # type: ignore[method-assign]
    MiAccount.mi_request = _patched_mi_request  # type: ignore[method-assign]

    _patch_xiaogpt_token_home()
    _PATCHED = True
    _LOGGER.info("已启用安全登录补丁，token=%s", get_token_path())


def _patch_xiaogpt_token_home() -> None:
    """xiaogpt 写死 ~/.mi.token，改为项目 token 路径。"""
    try:
        from xiaogpt.xiaogpt import MiGPT
    except Exception:
        return

    token_path = get_token_path()
    orig_init = MiGPT.__init__

    def _init(self, config):
        orig_init(self, config)
        self.mi_token_home = token_path

    MiGPT.__init__ = _init  # type: ignore[method-assign]
