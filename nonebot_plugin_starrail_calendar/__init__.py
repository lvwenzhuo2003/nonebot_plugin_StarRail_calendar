import logging
import nonebot

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from nonebot import get_bot, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Message, MessageSegment, ActionFailed
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from .config import *

from .utils import *
from .draw_calendar import *

__plugin_meta__ = PluginMetadata(
    name="StarRailCalendar",
    description="崩坏：星穹铁道活动日历",
    usage="srcl [on|off]|[time hh:mm]|[status]",
    extra={
        'author': 'TonyKun',
        'version': '1.1',
        'priority': 24,
        "srhelp": """\
查询活动日历: srcl
开启日历订阅：srcl on/off
指定订阅时间：srcl time HH:mm
查看订阅设置：srcl status
""",
    },
)

driver = nonebot.get_driver()
scheduler = AsyncIOScheduler()
calendar = on_command('srcl', aliases={"星穹日历", '星琼日历', '星铁日历', '崩铁日历'}, priority=24, block=True)


@driver.on_startup
async def _():
    scheduler.start()
    for group_id, group_data in load_data('data.json').items():
        scheduler.add_job(
            func=send_calendar,
            trigger='cron',
            hour=group_data['hour'],
            minute=group_data['minute'],
            id="starrail_calendar_" + group_id,
            args=(group_id, group_data),
            misfire_grace_time=10
        )


async def send_calendar(group_id, group_data):
    im = await generate_day_schedule('cn', viewport={"width": config.width, "height": config.height})
    await get_bot().send_group_msg(group_id=int(group_id), message=MessageSegment.image(im))


def update_group_schedule(group_id, group_data):
    group_id = str(group_id)
    if group_id not in group_data:
        return

    scheduler.add_job(
        func=send_calendar,
        trigger='cron',
        args=(group_id, group_data),
        id=f'starrail_calendar_{group_id}',
        replace_existing=True,
        hour=group_data[group_id]['hour'],
        minute=group_data[group_id]['minute'],
        misfire_grace_time=10
    )


@calendar.handle()
async def _(event: Union[GroupMessageEvent, MessageEvent], msg: Message = CommandArg()):
    import re
    if event.message_type == 'private':
        await calendar.finish('仅支持群聊模式下使用本指令')

    group_id = str(event.group_id)
    group_data = load_data('data.json')
    server = 'cn'
    fun = msg.extract_plain_text().strip()
    action = re.search(r'(?P<action>on|off|time|status|cardimage)', fun)
    if not fun:
        im = await generate_day_schedule(server, viewport={"width": config.width, "height": config.height})

        try:
            await calendar.finish(MessageSegment.image(im))
        except ActionFailed as e:
            logging.error(e)

    elif action:

        # 添加定时推送任务
        if action.group('action') == 'on':
            group_data[group_id] = {
                'server_list': [
                    str(server)
                ],
                'hour': 8,
                'minute': 0,
            }
            if event.message_type == 'guild':
                await calendar.finish("暂不支持频道内推送~")

            if scheduler.get_job('starrail_calendar_' + group_id):
                scheduler.remove_job("starrail_calendar_" + group_id)
            save_data(group_data, 'data.json')

            scheduler.add_job(
                func=send_calendar,
                trigger='cron',
                hour=8,
                minute=0,
                id="starrail_calendar_" + group_id,
                args=(group_id, group_data[group_id]),
                misfire_grace_time=10
            )

            await calendar.finish('星穹日历推送已开启', at_sender=True)

        # 关闭推送功能
        elif action.group('action') == 'off':
            del group_data[group_id]
            if scheduler.get_job("starrail_calendar_" + group_id):
                scheduler.remove_job("starrail_calendar_" + group_id)
            save_data(group_data, 'data.json')
            await calendar.finish('星穹日历推送已关闭', at_sender=True)

        # 设置推送时间
        elif action.group('action') == 'time':
            match = str(msg).split(" ")
            time = re.search(r'(\d{1,2}):(\d{2})', match[1]) or re.search(r'(\d{1,2})：(\d{2})', match[1])

            if time:
                if not time or len(time.groups()) < 2:
                    await calendar.finish("请指定推送时间", at_sender=True)
                else:
                    group_data[group_id]['hour'] = int(time.group(1))
                    group_data[group_id]['minute'] = int(time.group(2))
                    save_data(group_data, 'data.json')
                    update_group_schedule(group_id, group_data)

                    await calendar.finish(
                        f"推送时间已设置为: {group_data[group_id]['hour']}:{group_data[group_id]['minute']:02d}",
                        at_sender=True)

            else:
                timedateref = "https://docs.oracle.com/javase/7/docs/api/java/text/SimpleDateFormat.html"
                await calendar.finish(f"请给出正确的时间，格式为HH:mm，24小时制\n请参阅{timedateref}获取更多信息", at_sender=True)

        # 查询订阅推送状态
        elif action.group('action') == "status":
            try:
                server_list = group_data[group_id]['server_list']
                if group_data[group_id]['hour'] < 10:
                    hour = "0" + str(group_data[group_id]['hour'])
                else:
                    hour = str(group_data[group_id]['hour'])
                if group_data[group_id]['minute'] < 10:
                    minute = "0" + str(group_data[group_id]['minute'])
                else:
                    minute = str(group_data[group_id]['minute'])
                message = f'已为本群订阅{server}服务器的日历，时间为每天{hour}:{minute}'
                await calendar.finish(message)
            except KeyError as e:
                await calendar.finish("本群没有已订阅的日历")
