# -*- coding: utf-8 -*-
__plugin_name__ = "search_in_bilibili"
__openapi_version__ = "20231027"

from llmkira.sdk.func_calling import verify_openapi_version

verify_openapi_version(__plugin_name__, __openapi_version__)

import inscriptis
from llmkira.schema import RawMessage
from llmkira.sdk.func_calling import BaseTool, PluginMetadata
from llmkira.sdk.func_calling.schema import FuncPair
from llmkira.sdk.schema import Function
from llmkira.task import Task, TaskHeader
from loguru import logger
from pydantic import BaseModel

bilibili = Function(name=__plugin_name__, description="Search videos on bilibili.com(哔哩哔哩)")
bilibili.add_property(
    property_name="keywords",
    property_description="Keywords entered in the search box",
    property_type="string",
    required=True
)


async def search_on_bilibili(keywords):
    from bilibili_api import search
    logger.debug(f"Plugin:search_on_bilibili {keywords}")
    _result = await search.search_by_type(
        keyword=keywords,
        search_type=search.SearchObjectType.VIDEO,
        order_type=search.OrderVideo.TOTALRANK,
        page=1
    )
    _video_list = _result.get("result")
    if not _video_list:
        return "Search Not Success"
    _video_list = _video_list[:3]  # 只取前三
    _info = []
    for video in _video_list:
        _video_title = inscriptis.get_text(video.get("title"))
        _video_author = video.get("author")
        _video_url = video.get("arcurl")
        _video_tag = video.get("tag")
        _video_play = video.get("play")
        _video_info = f"(Title={_video_title},Author={_video_author},Link={_video_url},Love={_video_play})"
        _info.append(_video_info)
    return "\nHintData".join(_info)


class Bili(BaseModel):
    keywords: str

    class Config:
        extra = "allow"


class BiliBiliSearch(BaseTool):
    """
    搜索工具
    """
    silent: bool = True
    function: Function = bilibili
    keywords: list = ["哔哩哔哩", "b站", "B站", "视频", '搜索', '新闻', 'bilibili']
    require_auth: bool = False

    def pre_check(self):
        try:
            import bilibili_api
            return True
        except ImportError as e:
            logger.error(f"Plugin:bilibili:package <bilibili_api> not installed:{e}")
            return False

    def func_message(self, message_text, **kwargs):
        """
        如果合格则返回message，否则返回None，表示不处理
        """
        for i in self.keywords:
            if i in message_text:
                return self.function
        # 正则匹配
        if self.pattern:
            match = self.pattern.match(message_text)
            if match:
                return self.function
        return None

    async def failed(self, platform, task: TaskHeader, receiver, reason, **kwargs):
        try:
            _meta = task.task_meta.reply_notify(
                plugin_name=__plugin_name__,
                write_back=True,
                release_chain=True,
                callback=TaskHeader.Meta.Callback(
                    role="function",
                    name=__plugin_name__
                )
            )
            await Task(queue=platform).send_task(
                task=TaskHeader(
                    sender=task.sender,
                    receiver=receiver,
                    task_meta=_meta,
                    message=[
                        RawMessage(
                            user_id=receiver.user_id,
                            chat_id=receiver.chat_id,
                            text=f"Plugin {__plugin_name__} Run failed beacause {reason}"
                        )
                    ]
                )
            )
        except Exception as e:
            logger.error(e)

    async def callback(self, sign: str, task: TaskHeader, receiver: TaskHeader.Location, **kwargs):
        return True

    async def run(self, task: TaskHeader, receiver: TaskHeader.Location, arg, **kwargs):
        """
        处理message，返回message
        """
        env = kwargs.get("env", {})
        try:
            _set = Bili.parse_obj(arg)
            _search_result = await search_on_bilibili(_set.keywords)
            _meta = task.task_meta.reply_raw(
                plugin_name=__plugin_name__,
                callback=TaskHeader.Meta.Callback(
                    role="function",
                    name=__plugin_name__
                )
            )
            await Task(queue=receiver.platform).send_task(
                task=TaskHeader(
                    sender=task.sender,  # 继承发送者
                    receiver=receiver,  # 因为可能有转发，所以可以单配
                    task_meta=_meta,
                    message=[
                        RawMessage(
                            user_id=receiver.user_id,
                            chat_id=receiver.chat_id,
                            text=_search_result
                        )
                    ]
                )
            )
        except Exception as e:
            logger.exception(e)
            await self.failed(platform=receiver.platform, task=task, receiver=receiver, reason=str(e))


__plugin_meta__ = PluginMetadata(
    name=__plugin_name__,
    description="Search videos on bilibili.com(哔哩哔哩)",
    usage="bilibili search <keywords>",
    openapi_version=__openapi_version__,
    function={
        FuncPair(function=bilibili, tool=BiliBiliSearch)
    }
)
