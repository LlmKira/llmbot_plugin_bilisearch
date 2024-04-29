# -*- coding: utf-8 -*-
from typing import Union, Type, List

import inscriptis
from loguru import logger
from pydantic import BaseModel, Field
from pydantic import ConfigDict

__plugin_name__ = "search_in_bilibili"
__openapi_version__ = "20240416"

from llmkira.sdk.tools import verify_openapi_version  # noqa: E402

verify_openapi_version(__plugin_name__, __openapi_version__)  # noqa: E402
from llmkira.openai.cell import Tool, ToolCall, class_tool  # noqa: E402
from llmkira.openapi.fuse import resign_plugin_executor  # noqa: E402
from llmkira.sdk.tools import PluginMetadata  # noqa: E402
from llmkira.sdk.tools.schema import FuncPair, BaseTool  # noqa: E402
from llmkira.task import Task, TaskHeader  # noqa: E402
from llmkira.task.schema import Location, ToolResponse, EventMessage  # noqa: E402


class BiliBiliSearch(BaseModel):
    keywords: str = Field(description="question entered in the search website")
    model_config = ConfigDict(extra="allow")


@resign_plugin_executor(tool=BiliBiliSearch, handle_exceptions=(Exception,))
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


class BiliBiliSearch(BaseTool):
    """
    搜索工具
    """
    silent: bool = True
    function: Union[Tool, Type[BaseModel]] = BiliBiliSearch
    keywords: list = ["哔哩哔哩", "b站", "B站", "视频", '搜索', '新闻', 'bilibili']

    def require_auth(self, env_map: dict) -> bool:
        """
        Auth or not
        :param env_map: virtual env
        :return:
        """
        return False

    @classmethod
    def env_help_docs(cls, empty_env: List[str]) -> str:
        """
        Provide help message for environment variables
        :param empty_env: The environment variable list that not configured
        :return: The help message
        """
        message = ""
        return message

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

    async def failed(
            self,
            task: "TaskHeader",
            receiver: "Location",
            exception,
            env: dict,
            arg: dict,
            pending_task: "ToolCall",
            refer_llm_result: dict = None,
            **kwargs,
    ):
        meta = task.task_sign.reply(
            plugin_name=__plugin_name__,
            tool_response=[
                ToolResponse(
                    name=__plugin_name__,
                    function_response=f"Run Failed {exception}",
                    tool_call_id=pending_task.id,
                    tool_call=pending_task,
                )
            ],
        )
        await Task.create_and_send(
            queue_name=receiver.platform,
            task=TaskHeader(
                sender=task.sender,
                receiver=receiver,
                task_sign=meta,
                message=[
                    EventMessage(
                        user_id=receiver.user_id,
                        chat_id=receiver.chat_id,
                        text=f"🍖{__plugin_name__} Run Failed：{exception},report it to user.",
                    )
                ],
            ),
        )

    async def callback(
            self,
            task: "TaskHeader",
            receiver: "Location",
            env: dict,
            arg: dict,
            pending_task: "ToolCall",
            refer_llm_result: dict = None,
            **kwargs,
    ):
        return True

    async def run(
            self,
            task: "TaskHeader",
            receiver: "Location",
            arg: dict,
            env: dict,
            pending_task: "ToolCall",
            refer_llm_result: dict = None,
    ):
        """
        处理message，返回message
        """

        _set = BiliBiliSearch.model_validate(arg)
        _search_result = await search_on_bilibili(_set.keywords)
        _meta = task.task_sign.reprocess(
            plugin_name=__plugin_name__,
            tool_response=[
                ToolResponse(
                    name=__plugin_name__,
                    function_response=f"SearchData: {_search_result},Please give reference link when use it.",
                    tool_call_id=pending_task.id,
                    tool_call=pending_task,
                )
            ]
        )
        await Task.create_and_send(
            queue_name=receiver.platform,
            task=TaskHeader(
                sender=task.sender,  # 继承发送者
                receiver=receiver,  # 因为可能有转发，所以可以单配
                task_sign=_meta,
                message=[],
            ),
        )


__plugin_meta__ = PluginMetadata(
    name=__plugin_name__,
    description="Search videos on bilibili.com(哔哩哔哩)",
    usage="bilibili search <keywords>",
    openapi_version=__openapi_version__,
    function={
        FuncPair(function=class_tool(BiliBiliSearch), tool=BiliBiliSearch)
    }
)
