import discord
from discord.ext import commands
from discord.utils import get
import json
import os

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="c!",
    intents=intents,
    help_command=None
)

CONFIG_FILE = "rino_config.json"

TARGET_CHANNEL_ID = None
TARGET_YOUTUBE_LINK = None
TARGET_STREAM_PLAN = None
counting_active = False

message_list = []
reacted_messages = []

# ----------------------
# 설정 불러오기
# ----------------------
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        TARGET_CHANNEL_ID = data.get("TARGET_CHANNEL_ID")
        TARGET_YOUTUBE_LINK = data.get("TARGET_YOUTUBE_LINK")
        TARGET_STREAM_PLAN = data.get("TARGET_STREAM_PLAN")

# ----------------------
# 설정 저장 함수 (중복 제거)
# ----------------------
def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "TARGET_CHANNEL_ID": TARGET_CHANNEL_ID,
            "TARGET_YOUTUBE_LINK": TARGET_YOUTUBE_LINK,
            "TARGET_STREAM_PLAN": TARGET_STREAM_PLAN
        }, f)

# ----------------------
# 이벤트
# ----------------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# ----------------------
# 명령어
# ----------------------
@bot.command(name="채널설정", help="사용할 채널을 설정합니다.")
async def 채널설정(ctx, *, channel_name):
    global TARGET_CHANNEL_ID

    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send(f"'{channel_name}' 채널을 찾을 수 없습니다.")
        return

    TARGET_CHANNEL_ID = channel.id
    save_config()

    await ctx.send(f"채널이 <#{TARGET_CHANNEL_ID}> 로 설정되었습니다!")


@bot.command(name="유튜브설정", help="유튜브 링크를 설정합니다.")
async def 유튜브설정(ctx, *, youtube_link):
    global TARGET_YOUTUBE_LINK
    TARGET_YOUTUBE_LINK = youtube_link
    save_config()

    await ctx.send(f"유튜브 링크 설정 완료!")


@bot.command(name="유튜브", help="유튜브 채널을 보여줍니다.")
async def 유튜브(ctx):
    if TARGET_YOUTUBE_LINK:
        await ctx.send(TARGET_YOUTUBE_LINK)
    else:
        await ctx.send("유튜브 링크가 설정되지 않았습니다.")


@bot.command(name="방송일정설정", help="방송 일정을 설정합니다.")
async def 방송일정설정(ctx, *, stream_plan):
    global TARGET_STREAM_PLAN
    TARGET_STREAM_PLAN = stream_plan
    save_config()

    await ctx.send("방송 일정 설정 완료!")


@bot.command(name="방송일정", help="방송 일정을 확인합니다.")
async def 방송일정(ctx):
    if TARGET_STREAM_PLAN:
        await ctx.send(TARGET_STREAM_PLAN)
    else:
        await ctx.send("방송 일정이 없습니다.")


@bot.command(name="시참시작", help="시참 받기를 시작합니다.")
async def start_count(ctx):
    global counting_active, message_list, reacted_messages

    if TARGET_CHANNEL_ID is None:
        await ctx.send("먼저 채널 설정해주세요.")
        return

    counting_active = True
    message_list = []
    reacted_messages = []

    await ctx.send("시참 시작!")


@bot.command(name="시참끝", help="시참 받기를 종료합니다.")
async def stop_count(ctx):
    global counting_active
    counting_active = False
    await ctx.send("시참 종료!")




# ----------------------
# 메시지 이벤트
# ----------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if counting_active and TARGET_CHANNEL_ID and message.channel.id == TARGET_CHANNEL_ID:
        message_list.append(message)

        if len(message_list) % 4 == 0:
            await message.add_reaction("✅")
            reacted_messages.append(message)

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    if TARGET_CHANNEL_ID and message.channel.id == TARGET_CHANNEL_ID:
        if message in message_list:
            message_list.remove(message)

# ----------------------
# 실행 (환경변수 사용)
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("토큰 없음")
else:
    bot.run(TOKEN)
