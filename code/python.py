import ast
import os
import time

from android_utils import run_on_ui_thread
from base_plugin import BasePlugin
from client_utils import (
    get_last_fragment,
    get_messages_controller,
    get_user_config,
    run_on_queue,
    send_document,
)
from file_utils import (
    delete_file,
    ensure_dir_exists,
    get_cache_dir,
    get_plugins_dir,
    read_file,
    write_file,
)
from typing import Any, Dict
from ui.bulletin import BulletinHelper
from ui.settings import Divider, Header, Switch, Text

from java import dynamic_proxy, jclass
from android.os import Bundle

__id__ = "plugin_share"
__name__ = "Plugin Share"
__description__ = "Share all installed plugins at once to any chat."
__author__ = "@itNotMax - @MaxExteraPlugins"
__version__ = "2.0.3"
__min_version__ = "12.10.6"
__icon__ = "MaxExteraPluginsStickers/12"


def _parse_plugin_meta(file_path: str) -> Dict[str, str]:
    meta = {}
    try:
        source = read_file(file_path)
        if not source:
            return meta
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in (
                        "__name__",
                        "__description__",
                        "__version__",
                        "__author__",
                        "__id__",
                    ):
                        if isinstance(node.value, ast.Constant):
                            meta[target.id] = str(node.value.value)
    except Exception:
        pass
    return meta


def _build_caption(meta: Dict[str, str], file_name: str,
                   show_name=True, show_version=True,
                   show_desc=True, show_author=True) -> str:
    parts = []
    name = meta.get("__name__", "")
    version = meta.get("__version__", "")
    description = meta.get("__description__", "")
    author = meta.get("__author__", "")

    if show_name and name:
        line = f"📦 {name}"
        if show_version and version:
            line += f"  v{version}"
        parts.append(line)
    elif show_version and version:
        parts.append(f"📦 v{version}")

    if show_desc and description:
        parts.append(f"📝 {description}")
    if show_author and author:
        parts.append(f"👤 {author}")

    if not parts:
        parts.append(f"📦 {file_name}")

    return "\n".join(parts)


def _build_topic_reply(peer_id, topic_id):
    if not topic_id or topic_id <= 1:
        return None
    try:
        from org.telegram.messenger import MessageObject, UserConfig
        chat_id = int(-peer_id)
        topic = get_messages_controller().getTopicsController().findTopic(chat_id, int(topic_id))
        if topic is None or topic.topicStartMessage is None:
            return None
        obj = MessageObject(int(UserConfig.selectedAccount), topic.topicStartMessage, False, False)
        if obj.messageOwner is None:
            return None
        _ = obj.getId()
        obj.isTopicMainMessage = True
        return obj
    except Exception:
        return None


def _collect_plugin_files(plugins_dir: str):
    plugin_files = []
    py_files = []
    try:
        for entry in os.listdir(plugins_dir):
            full = os.path.join(plugins_dir, entry)
            if not os.path.isfile(full):
                continue
            if entry.startswith(".") or entry.startswith("_"):
                continue
            lower = entry.lower()
            if lower.endswith(".plugin"):
                plugin_files.append(full)
            elif lower.endswith(".py"):
                py_files.append(full)
    except Exception:
        pass
    return plugin_files if plugin_files else py_files


def _prepare_share_file(source_path: str, cache_dir: str):
    lower = source_path.lower()
    if lower.endswith(".plugin"):
        return source_path, False

    content = read_file(source_path)
    if content is None:
        return source_path, False

    base_name = os.path.basename(source_path)
    plugin_name = base_name.rsplit(".py", 1)[0] if base_name.lower().endswith(".py") else base_name
    share_path = os.path.join(cache_dir, plugin_name + ".plugin")
    write_file(share_path, content)
    return share_path, True



# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================

# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================

# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================
class AuthorChannelHelper:
    CONFIG_URL = "https://raw.githubusercontent.com/MaxExteraPlugins/config/main/links.json"

    DEFAULT_LINKS = {
        "channel_username": "MaxExteraPlugins",
        "channel_url": "https://t.me/MaxExteraPlugins",
        "header": {"ru": "MaxExteraPlugins", "en": "MaxExteraPlugins"},
        "buttons": [
            {"title": {"ru": "Канал автора", "en": "Author's Channel"}, "icon": "msg_channel", "url": "https://t.me/MaxExteraPlugins"},
            {"title": {"ru": "Поддержать автора", "en": "Support author"}, "icon": "msg_share", "url": "https://t.me/itNotMax"},
            {"title": {"ru": "Сообщить о баге", "en": "Report a bug"}, "icon": "msg_help", "url": "https://t.me/itNotMax"}
        ]
    }

    _TEXTS = {
        "install_card_title": {"ru": "Подпишитесь на канал", "en": "Subscribe to channel"},
        "install_card_msg": {
            "ru": (
                "Мы делаем плагины бесплатными и доступными для всех: пожалуйста, "
                "поддержите нас подпиской на официальный канал @MaxExteraPlugins.\n\n"
                "Там публикуются обновления, важные новости и анонсы новых плагинов."
            ),
            "en": (
                "We keep our plugins free and accessible for everyone: please "
                "support us by subscribing to our official channel @MaxExteraPlugins.\n\n"
                "Updates, news, and new plugin announcements are published there."
            )
        },
        "open_channel_btn": {"ru": "Перейти на канал", "en": "Open channel"},
        "remind_later_btn": {"ru": "Напомнить позже", "en": "Remind later"},
        "never_show_btn": {"ru": "Больше не показывать", "en": "Don't show again"},
        "sub_thank_you": {"ru": "Спасибо за подписку на наш канал!", "en": "Thank you for subscribing to our channel!"},
        "settings_channel": {"ru": "Канал автора", "en": "Author's Channel"},
        "settings_donate": {"ru": "Поддержать автора", "en": "Support author"},
        "settings_bug_report": {"ru": "Сообщить о баге", "en": "Report a bug"}
    }

    @classmethod
    def is_ru(cls) -> bool:
        try:
            from org.telegram.messenger import LocaleController
            lang = str(LocaleController.getInstance().getCurrentLocale().getLanguage() or "").lower()
            return lang in ("ru", "be", "uk", "kk")
        except Exception:
            return True

    @classmethod
    def tr(cls, key: str) -> str:
        entry = cls._TEXTS.get(key, {})
        return entry.get("ru" if cls.is_ru() else "en", entry.get("en", key))

    def __init__(self, plugin, icon_sticker=None):
        self.plugin = plugin
        self.icon_sticker = icon_sticker or getattr(plugin, "__icon__", "MaxExteraPluginsStickers/1")
        self._stopped = False
        self._active_dialog = None

    def on_load(self):
        self._stopped = False
        self._active_dialog = None
        self._load_remote_links_async()
        self._check_initial_subscription_flow()

    def on_event(self, event_type):
        try:
            name = str(event_type).upper()
            if name.endswith("START") or name.endswith("RESUME"):
                if self.is_subscribed() and not self.plugin.get_setting("was_subscribed", False):
                    self.plugin.set_setting("was_subscribed", True)
                    self._dismiss_active_dialog()
                    self._notify_subscribed()
        except Exception:
            pass

    def on_unload(self):
        self._stopped = True
        self._dismiss_active_dialog()

    def is_allowed(self) -> bool:
        return True

    def _get_links(self) -> dict:
        raw = self.plugin.get_setting("remote_links_cache", None)
        if raw:
            try:
                import json
                data = json.loads(raw)
                if isinstance(data, dict): return data
            except Exception:
                pass
        return self.DEFAULT_LINKS

    def _load_remote_links_async(self):
        def worker():
            try:
                import urllib.request, json
                req = urllib.request.Request(self.CONFIG_URL, headers={"User-Agent": "MaxExteraPlugins"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if isinstance(data, dict):
                            self.plugin.set_setting("remote_links_cache", json.dumps(data))
                            self._resolve_channel_in_telegram(data.get("channel_username", "MaxExteraPlugins"))
            except Exception:
                pass
        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _open_url(self, url: str, view=None):
        try:
            from org.telegram.messenger.browser import Browser
            from org.telegram.messenger import ApplicationLoader
            from client_utils import get_last_fragment
            ctx = None
            if view is not None:
                ctx = view.getContext()
            if ctx is None:
                frag = get_last_fragment()
                if frag is not None:
                    ctx = frag.getParentActivity()
            if ctx is None:
                ctx = ApplicationLoader.applicationContext
            Browser.openUrl(ctx, url)
        except Exception:
            pass

    def _resolve_channel_in_telegram(self, username: str):
        try:
            from org.telegram.messenger import UserConfig, MessagesController
            from org.telegram.tgnet import TLRPC, ConnectionsManager, RequestDelegate
            clean_user = username.lstrip("@")
            acc = int(UserConfig.selectedAccount)
            mc = MessagesController.getInstance(acc)
            if not mc: return
            req = TLRPC.TL_contacts_resolveUsername()
            req.username = clean_user
            helper_ref = self
            class Delegate(RequestDelegate):
                def run(self, response, error):
                    if error is None and response is not None:
                        chats = getattr(response, "chats", None)
                        if chats is not None and chats.size() > 0:
                            for a in range(UserConfig.MAX_ACCOUNT_COUNT):
                                try:
                                    if UserConfig.getInstance(a).isClientActivated():
                                        MessagesController.getInstance(a).putChats(chats, False)
                                except Exception:
                                    pass
                            c = chats.get(0)
                            cid = getattr(c, "id", 0)
                            if cid > 0:
                                helper_ref.plugin.set_setting("resolved_channel_id", int(cid))
            ConnectionsManager.getInstance(acc).sendRequest(req, Delegate())
        except Exception:
            pass

    def is_subscribed(self) -> bool:
        try:
            from org.telegram.messenger import UserConfig, MessagesController, MessagesStorage
            from java.lang import Long as JLong
            links = self._get_links()
            target = str(links.get("channel_username", "MaxExteraPlugins") or "MaxExteraPlugins").lower().lstrip("@")
            saved_cid = int(self.plugin.get_setting("resolved_channel_id", 0) or 0)

            for acc in range(UserConfig.MAX_ACCOUNT_COUNT):
                try:
                    uconf = UserConfig.getInstance(acc)
                    if not uconf.isClientActivated():
                        continue

                    mc = MessagesController.getInstance(acc)
                    storage = MessagesStorage.getInstance(acc)

                    # 1. In-memory check by resolved_channel_id
                    if saved_cid and mc is not None:
                        try:
                            c = mc.getChat(JLong(saved_cid))
                            if c is not None:
                                left = bool(getattr(c, "left", True))
                                kicked = bool(getattr(c, "kicked", False))
                                if not left and not kicked:
                                    return True
                        except Exception:
                            pass

                    # 2. In-memory check by username
                    if mc is not None:
                        try:
                            chat = mc.getUserOrChat(target)
                            if chat is not None:
                                cid = int(getattr(chat, "id", 0) or 0)
                                if cid and not saved_cid:
                                    saved_cid = cid
                                    self.plugin.set_setting("resolved_channel_id", cid)
                                left = bool(getattr(chat, "left", True))
                                kicked = bool(getattr(chat, "kicked", False))
                                if not left and not kicked:
                                    return True
                        except Exception:
                            pass

                    # 3. In-memory dialogs check
                    if mc is not None:
                        try:
                            dialog_lists = []
                            d_chan = getattr(mc, "dialogsChannelsOnly", None)
                            if d_chan is not None and d_chan.size() > 0:
                                dialog_lists.append(d_chan)
                            d_all = getattr(mc, "allDialogs", None)
                            if d_all is not None and d_all.size() > 0:
                                dialog_lists.append(d_all)

                            for d_list in dialog_lists:
                                limit = min(d_list.size(), 300)
                                for i in range(limit):
                                    d = d_list.get(i)
                                    did = getattr(d, "id", 0)
                                    if did < 0:
                                        cid = -did
                                        if saved_cid and cid == saved_cid:
                                            c = mc.getChat(JLong(cid))
                                            if c is not None:
                                                left = bool(getattr(c, "left", True))
                                                kicked = bool(getattr(c, "kicked", False))
                                                if not left and not kicked:
                                                    return True
                                        else:
                                            c = mc.getChat(JLong(cid))
                                            if c is not None:
                                                uname = str(getattr(c, "username", "") or "").lower()
                                                if uname == target:
                                                    if not saved_cid:
                                                        saved_cid = cid
                                                        self.plugin.set_setting("resolved_channel_id", cid)
                                                    left = bool(getattr(c, "left", True))
                                                    kicked = bool(getattr(c, "kicked", False))
                                                    if not left and not kicked:
                                                        return True
                        except Exception:
                            pass

                    # 4. Storage check (SQLite on disk)
                    if storage is not None:
                        if saved_cid:
                            try:
                                if storage.containsLocalDialog(JLong(-saved_cid)):
                                    c_sync = storage.getChatSync(JLong(saved_cid))
                                    if c_sync is not None:
                                        left = bool(getattr(c_sync, "left", True))
                                        kicked = bool(getattr(c_sync, "kicked", False))
                                        if not left and not kicked:
                                            return True
                                    else:
                                        return True
                            except Exception:
                                pass

                        try:
                            db = storage.getDatabase()
                            if db is not None:
                                if saved_cid:
                                    try:
                                        cur = db.queryFinalized("SELECT did FROM dialogs WHERE did = ?", [JLong(-saved_cid)])
                                        if cur is not None:
                                            has_row = bool(cur.next())
                                            cur.dispose()
                                            if has_row:
                                                return True
                                    except Exception:
                                        pass

                                try:
                                    cur = db.queryFinalized("SELECT uid, name FROM chats WHERE LOWER(name) LIKE ?", ["%" + target + "%"])
                                    if cur is not None:
                                        while cur.next():
                                            c_id = cur.longValue(0)
                                            if c_id > 0:
                                                if not saved_cid:
                                                    saved_cid = int(c_id)
                                                    self.plugin.set_setting("resolved_channel_id", saved_cid)
                                                cur_d = db.queryFinalized("SELECT did FROM dialogs WHERE did = ?", [JLong(-c_id)])
                                                if cur_d is not None:
                                                    in_dlg = bool(cur_d.next())
                                                    cur_d.dispose()
                                                    if in_dlg:
                                                        cur.dispose()
                                                        return True
                                        cur.dispose()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def prepend_settings(self, original_items=None) -> list:
        from ui.settings import Header, Text, Divider

        if original_items and any(getattr(x, "text", "") == "MaxExteraPlugins" for x in original_items if type(x).__name__ == "Header"):
            return original_items

        links = self._get_links()
        buttons_config = links.get("buttons")

        author_items = []
        if isinstance(buttons_config, list):
            for btn in buttons_config:
                if not isinstance(btn, dict): continue
                raw_url = btn.get("url")
                if isinstance(raw_url, dict):
                    keys = [
                        getattr(self.plugin, "id", None),
                        globals().get("__id__", None),
                        globals().get("__name__", None),
                        self.plugin.__class__.__name__
                    ]
                    keys += [k.lower() for k in keys if isinstance(k, str)]
                    resolved_url = ""
                    for k in keys:
                        if k and k in raw_url:
                            resolved_url = str(raw_url[k] or "").strip()
                            if resolved_url:
                                break
                    url = resolved_url
                elif isinstance(raw_url, str):
                    url = raw_url.strip()
                else:
                    url = ""

                if not url: continue

                title_data = btn.get("title")
                if isinstance(title_data, dict):
                    title = title_data.get("ru" if self.is_ru() else "en") or title_data.get("en") or title_data.get("ru") or ""
                elif isinstance(title_data, str) and title_data:
                    title = title_data
                else:
                    title = btn.get("title_ru" if self.is_ru() else "title_en") or btn.get("title_ru") or btn.get("title_en") or ""

                if not title: continue
                icon = str(btn.get("icon") or "msg_channel").strip()

                def make_click(u):
                    return lambda v=None: self._open_url(u, v)

                author_items.append(Text(text=title, icon=icon, on_click=make_click(url)))
        else:
            for k, text_key, icon_name in [
                ("channel_url", "settings_channel", "msg_channel"),
                ("donate_url", "settings_donate", "msg_share"),
                ("bug_report_url", "settings_bug_report", "msg_help")
            ]:
                u = str(links.get(k) or "").strip()
                if u:
                    author_items.append(Text(text=self.tr(text_key), icon=icon_name, on_click=lambda v=None, target_u=u: self._open_url(target_u, v)))

        res = []
        if author_items:
            hdr = links.get("header") or "MaxExteraPlugins"
            if isinstance(hdr, dict):
                hdr_text = hdr.get("ru" if self.is_ru() else "en") or hdr.get("ru") or hdr.get("en") or "MaxExteraPlugins"
            else:
                hdr_text = str(hdr)
            res.append(Header(text=hdr_text))
            res.extend(author_items)
            res.append(Divider())

        cleaned_items = []
        if original_items:
            skipping_info = False
            for item in original_items:
                item_cls = type(item).__name__
                if item_cls == "Header":
                    txt = str(getattr(item, "text", "") or getattr(item, "title", "") or "").lower()
                    if "информ" in txt or "inform" in txt:
                        skipping_info = True
                        continue
                    else:
                        skipping_info = False
                elif skipping_info and item_cls == "Divider":
                    skipping_info = False
                    continue

                if not skipping_info:
                    cleaned_items.append(item)

        res.extend(cleaned_items)
        return res

    def _dismiss_active_dialog(self):
        try:
            if self._active_dialog is not None:
                self._active_dialog.dismiss()
        except Exception:
            pass
        self._active_dialog = None

    def _is_dialog_active(self) -> bool:
        try:
            if self._active_dialog is not None:
                return bool(self._active_dialog.isShowing())
        except Exception:
            pass
        return False

    def _notify_subscribed(self):
        try:
            from ui.bulletin import BulletinHelper
            BulletinHelper.show_success(self.tr("sub_thank_you"))
        except Exception:
            pass

    def _check_initial_subscription_flow(self):
        def flow():
            try:
                if self.plugin.get_setting("never_show_sub_prompt", False):
                    return

                current_ver = str(getattr(self.plugin, "__version__", globals().get("__version__", "1.0.0")) or "1.0.0")
                last_prompted_ver = self.plugin.get_setting("last_prompted_version", None)

                # Only show on install (last_prompted_ver is None) or update (last_prompted_ver != current_ver)
                if last_prompted_ver is not None and str(last_prompted_ver) == current_ver:
                    return

                if self.is_subscribed():
                    self.plugin.set_setting("last_prompted_version", current_ver)
                    self.plugin.set_setting("was_subscribed", True)
                    return

                self._show_subscription_prompt(current_ver)
            except Exception:
                pass
        from android_utils import run_on_ui_thread
        run_on_ui_thread(flow, 1500)

    def _create_card_content(self, act, title_text, message_text):
        try:
            from android.widget import LinearLayout, TextView, ImageView
            from android.view import Gravity
            from org.telegram.messenger import AndroidUtilities
            from org.telegram.ui.ActionBar import Theme
            from client_utils import create_sticker_drawable

            dp = AndroidUtilities.dp

            layout = LinearLayout(act)
            layout.setOrientation(LinearLayout.VERTICAL)
            layout.setGravity(Gravity.CENTER_HORIZONTAL)
            layout.setPadding(dp(24), dp(20), dp(24), dp(10))

            sticker_drawable = None
            if self.icon_sticker:
                try:
                    sticker_drawable = create_sticker_drawable(self.icon_sticker, dp(120), dp(120))
                except Exception:
                    pass

            if sticker_drawable is not None:
                iv = ImageView(act)
                iv.setImageDrawable(sticker_drawable)
                lp_iv = LinearLayout.LayoutParams(dp(120), dp(120))
                lp_iv.gravity = Gravity.CENTER_HORIZONTAL
                lp_iv.bottomMargin = dp(14)
                layout.addView(iv, lp_iv)

            if title_text:
                tt = TextView(act)
                tt.setText(title_text)
                tt.setTextSize(19.0)
                tt.setTypeface(AndroidUtilities.bold())
                tt.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
                tt.setGravity(Gravity.CENTER_HORIZONTAL)
                lp_t = LinearLayout.LayoutParams(-1, -2)
                lp_t.bottomMargin = dp(8)
                layout.addView(tt, lp_t)

            if message_text:
                mt = TextView(act)
                mt.setText(message_text)
                mt.setTextSize(15.0)
                mt.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
                mt.setLineSpacing(float(dp(3)), 1.0)
                mt.setGravity(Gravity.CENTER_HORIZONTAL)
                lp_m = LinearLayout.LayoutParams(-1, -2)
                mt.setLayoutParams(lp_m)
                layout.addView(mt)

            return layout
        except Exception:
            return None

    def _show_subscription_prompt(self, current_ver: str):
        def show():
            try:
                if self._is_dialog_active(): return
                from client_utils import get_last_fragment
                frag = get_last_fragment()
                if not frag: return
                act = frag.getParentActivity()
                if not act: return

                links = self._get_links()
                url = links.get("channel_url", "https://t.me/MaxExteraPlugins")

                from ui.alert import AlertDialogBuilder
                b = AlertDialogBuilder(act)
                content = self._create_card_content(act, self.tr("install_card_title"), self.tr("install_card_msg"))
                if content is not None:
                    b.set_view(content)
                else:
                    b.set_title(self.tr("install_card_title"))
                    b.set_message(self.tr("install_card_msg"))

                def on_open_channel(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("last_prompted_version", current_ver)
                    self._open_url(url)

                def on_remind_later(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("last_prompted_version", current_ver)

                def on_never_show(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("never_show_sub_prompt", True)
                    self.plugin.set_setting("last_prompted_version", current_ver)

                b.set_positive_button(self.tr("open_channel_btn"), on_open_channel)
                b.set_neutral_button(self.tr("remind_later_btn"), on_remind_later)
                b.set_negative_button(self.tr("never_show_btn"), on_never_show)

                def on_dismiss(builder):
                    self.plugin.set_setting("last_prompted_version", current_ver)
                try:
                    b.set_on_dismiss_listener(on_dismiss)
                except Exception:
                    pass

                self._active_dialog = b.show()
                self.plugin.set_setting("last_prompted_version", current_ver)
            except Exception:
                pass
        from android_utils import run_on_ui_thread
        run_on_ui_thread(show)

class PluginExportPlugin(BasePlugin):

    def on_app_event(self, event_type):
        if hasattr(self, "_author_helper"):
            self._author_helper.on_event(event_type)

    def on_plugin_load(self):
        self._author_helper = AuthorChannelHelper(self, icon_sticker="MaxExteraPluginsStickers/12")
        self._author_helper.on_load()
        pass

    def on_plugin_unload(self):
        if hasattr(self, "_author_helper"):
            self._author_helper.on_unload()
        pass

    def create_settings(self):
        try:
            items = self._inner_create_settings()
        except Exception:
            items = []
        if hasattr(self, '_author_helper'):
            return self._author_helper.prepend_settings(items)
        return items

    def _inner_create_settings(self):
        return [
            Header(text="Caption"),
            Switch(
                key="include_caption",
                text="Add caption",
                default=True,
                subtext="Attach metadata as a caption.",
                icon="msg_text",
            ),
            Switch(
                key="show_name",
                text="Plugin name",
                default=True,
                icon="msg_openprofile",
            ),
            Switch(
                key="show_version",
                text="Plugin version",
                default=True,
                icon="msg_info",
            ),
            Switch(
                key="show_desc",
                text="Plugin description",
                default=True,
                icon="msg_log",
            ),
            Switch(
                key="show_author",
                text="Plugin author",
                default=True,
                icon="msg_contacts",
            ),
            Divider(),
            Header(text="Export"),
            Text(
                text="Export to Saved Messages",
                icon="msg_saved",
                on_click=lambda v: self._export_to_saved(),
            ),
            Text(
                text="Export to Another Chat",
                icon="msg_forward",
                on_click=lambda v: self._open_chat_picker(),
            ),
        ]

    def _open_chat_picker(self):
        plugin_ref = self

        def _do_open():
            try:
                fragment = get_last_fragment()
                if not fragment:
                    BulletinHelper.show_error("No active fragment.")
                    return

                DialogsActivity = jclass("org.telegram.ui.DialogsActivity")
                DelegateInterface = jclass(
                    "org.telegram.ui.DialogsActivity$DialogsActivityDelegate"
                )

                class ChatPickerDelegate(dynamic_proxy(DelegateInterface)):
                    def __init__(self):
                        super().__init__()

                    def didSelectDialogs(self, frag, dids, message, param,
                                         notify, scheduleDate, scheduleRepeatPeriod,
                                         topicsFragment):
                        try:
                            if dids is None or dids.size() == 0:
                                return False

                            first = dids.get(0)
                            if hasattr(first, "dialogId"):
                                peer_id = int(first.dialogId)
                                topic_id = int(first.topicId) if hasattr(first, "topicId") else 0
                            else:
                                peer_id = int(first)
                                topic_id = 0

                            reply_msg = _build_topic_reply(peer_id, topic_id)

                            if topicsFragment is not None:
                                try:
                                    topicsFragment.removeSelfFromStack()
                                except Exception:
                                    pass
                            try:
                                frag.removeSelfFromStack()
                            except Exception:
                                pass

                            plugin_ref._start_export(peer_id, reply_msg)
                        except Exception:
                            pass
                        return True

                    def canSelectStories(self):
                        return False

                    def didSelectStories(self, frag):
                        return False

                args = Bundle()
                args.putBoolean("onlySelect", True)
                args.putInt("dialogsType", 3)
                args.putBoolean("canSelectTopics", True)
                args.putString("selectAlertString", "Send plugins to %1$s?")
                args.putString("selectAlertStringGroup", "Send plugins to %1$s?")

                dialogs_fragment = DialogsActivity(args)
                dialogs_fragment.setDelegate(ChatPickerDelegate())
                fragment.presentFragment(dialogs_fragment)

            except Exception as e:
                BulletinHelper.show_error(f"Failed to open picker: {e}")

        run_on_ui_thread(_do_open)

    def _export_to_saved(self):
        user_cfg = get_user_config()
        current_user = user_cfg.getCurrentUser()
        if not current_user:
            run_on_ui_thread(
                lambda: BulletinHelper.show_error("Cannot determine current user.")
            )
            return
        self._start_export(current_user.id, None)

    def _start_export(self, peer_id, reply_msg):
        run_on_queue(lambda: self._do_export(peer_id, reply_msg))

    def _do_export(self, peer_id, reply_msg):
        try:
            plugins_dir = get_plugins_dir()
            plugin_files = _collect_plugin_files(plugins_dir)

            if not plugin_files:
                run_on_ui_thread(
                    lambda: BulletinHelper.show_error("No plugin files found.")
                )
                return

            include_caption = self.get_setting("include_caption", True)
            show_name = self.get_setting("show_name", True)
            show_version = self.get_setting("show_version", True)
            show_desc = self.get_setting("show_desc", True)
            show_author = self.get_setting("show_author", True)

            share_cache_dir = os.path.join(get_cache_dir(), "plugin_share")
            ensure_dir_exists(share_cache_dir)
            temp_paths = []

            sent_count = 0
            try:
                for source_path in plugin_files:
                    file_name = os.path.basename(source_path)
                    send_path, is_temp = _prepare_share_file(source_path, share_cache_dir)
                    if is_temp:
                        temp_paths.append(send_path)

                    caption = ""
                    if include_caption:
                        meta = _parse_plugin_meta(source_path)
                        caption = _build_caption(
                            meta, file_name,
                            show_name, show_version,
                            show_desc, show_author,
                        )

                    try:
                        if reply_msg is not None:
                            send_document(
                                peer_id, send_path, caption=caption,
                                replyToMsg=reply_msg, replyToTopMsg=reply_msg,
                            )
                        else:
                            send_document(peer_id, send_path, caption=caption)
                        sent_count += 1
                        time.sleep(0.5)
                    except Exception:
                        try:
                            send_document(peer_id, send_path, caption=caption)
                            sent_count += 1
                        except Exception:
                            pass
            finally:
                for temp_path in temp_paths:
                    try:
                        delete_file(temp_path)
                    except Exception:
                        pass

            total = sent_count
            run_on_ui_thread(
                lambda: BulletinHelper.show_success(f"Sent {total} plugin(s) ✓")
            )

        except Exception as e:
            err = str(e)
            run_on_ui_thread(
                lambda: BulletinHelper.show_error(f"Export failed: {err}")
            )
