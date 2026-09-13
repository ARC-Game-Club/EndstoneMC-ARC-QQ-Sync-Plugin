"""
事件处理模块
负责进服/离服/聊天的 QQ 群同步（经弧光消息中心）。
游戏时长 / 进服次数由 ARCCore 维护。
"""

from endstone.event import (
    event_handler,
    PlayerChatEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
)
import threading


class EventHandlers:
    """事件处理器 —— QQ 同步；时长统计委托 ARCCore。"""

    def __init__(self, plugin):
        self.plugin = plugin
        self.logger = plugin.logger

    def _resolve_display_name(self, player) -> str:
        """Prefer ARCCore title/guild display label when available."""
        try:
            arc = self.plugin.server.plugin_manager.get_plugin("arc_core")
            if arc is not None and hasattr(arc, "format_player_display_label_with_guild"):
                equipped = None
                if hasattr(arc, "title_system") and arc.title_system is not None:
                    equipped = arc.title_system.get_equipped_title(player)
                return arc.format_player_display_label_with_guild(
                    player.name, equipped, str(player.xuid)
                )
        except Exception as e:
            self.logger.debug(f"resolve display name via ARCCore failed: {e}")
        return player.name

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent):
        """玩家加入：同步 QQ 群；改名检测；时长由 ARCCore 记录。"""
        try:
            player = event.player
            player_name = player.name
            player_xuid = player.xuid

            self.logger.info(f"玩家 {player_name} (XUID: {player_xuid}) 加入游戏")

            plugin = self.plugin
            xuid = player_xuid
            name = player_name

            def _sync_name():
                try:
                    existing_player = plugin.data_manager.get_player_by_xuid(xuid)
                    if existing_player and existing_player.get("name") != name:
                        old_name = existing_player.get("name")
                        plugin.data_manager.update_player_name(old_name, name, xuid)
                except Exception as rpc_err:
                    self.logger.warning(f"进服后台同步玩家名失败: {rpc_err}")

            threading.Thread(
                target=_sync_name, daemon=True, name="QQSync-JoinRPC"
            ).start()

            display_name = self._resolve_display_name(player)
            # 等 ARCCore 向主服上报进服次数后再拉进度展示（从服含同步 RTT）。

            def _send_join():
                cached = getattr(plugin, "_stats_cache", None)
                if isinstance(cached, dict):
                    cached.pop(name, None)
                plugin.api_send_event("join", display_name, name)

            plugin.server.scheduler.run_task(plugin, _send_join, delay=40)

        except Exception as e:
            self.logger.error(f"处理玩家加入事件失败: {e}")

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        """玩家离开：同步 QQ 群；时长由 ARCCore 结算。"""
        try:
            player = event.player
            player_name = player.name
            player_xuid = player.xuid

            self.logger.info(f"玩家 {player_name} (XUID: {player_xuid}) 离开游戏")

            display_name = self._resolve_display_name(player)
            plugin = self.plugin
            name = player_name

            def _send_quit():
                cached = getattr(plugin, "_stats_cache", None)
                if isinstance(cached, dict):
                    cached.pop(name, None)
                plugin.api_send_event("quit", display_name, name)

            # 等 ARCCore 把本次会话时长上报主服后再展示累计时长
            plugin.server.scheduler.run_task(plugin, _send_quit, delay=40)

        except Exception as e:
            self.logger.error(f"处理玩家离开事件失败: {e}")

    @event_handler
    def on_player_chat(self, event: PlayerChatEvent):
        """玩家聊天：同步 QQ 群（不做刷屏/关键词拦截）。"""
        try:
            player = event.player
            message = event.message

            if message.startswith("/"):
                return

            # ARCCore cancels PlayerChatEvent to rebroadcast styled chat; still
            # forward to QQ here.
            display_name = self._resolve_display_name(player)
            self.plugin.api_send_event("chat", display_name, player.name, message)

        except Exception as e:
            self.logger.error(f"处理玩家聊天事件失败: {e}")
