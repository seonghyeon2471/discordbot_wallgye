import discord
from discord.ext import commands
from discord.utils import get
import json
import os
import yt_dlp as youtube_dl
from discord import FFmpegPCMAudio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="c!", intents=intents, help_command=None)

CONFIG_FILE = "rino_config.json"
TARGET_CHANNEL_ID = None
TARGET_YOUTUBE_LINK = None
TARGET_STREAM_PLAN = None
counting_active = False

message_list = []
reacted_messages = []
song_queue = []

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
# 설정 저장 함수
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
# 음성 채널 명령어
# ----------------------
@bot.command(name="join", help="봇을 음성채널로 데려옵니다.")
async def join_voice(ctx):
    if ctx.author.voice is None:
        await ctx.send("먼저 음성 채널에 들어가 있어야 합니다!")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"{channel.name} 채널로 들어왔어요!")

@bot.command(name="exit", help="봇을 음성채널에서 퇴장시킵니다.")
async def leave_voice(ctx):
    if ctx.voice_client is None:
        await ctx.send("저는 현재 음성 채널에 없어요.")
        return
    await ctx.voice_client.disconnect()
    await ctx.send("음성 채널에서 나왔어요!")

# ----------------------
# 유튜브 대기열 + 제어
# ----------------------
def play_next(ctx):
    if len(song_queue) == 0:
        return

    url = song_queue.pop(0)
    ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']

    ctx.voice_client.stop()

    ctx.voice_client.play(
        FFmpegPCMAudio(
            audio_url,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        ),
        after=lambda e: play_next(ctx)
    )

    bot.loop.create_task(ctx.send(f"{info['title']} 재생 시작!"))

@bot.command(name="play", help="유튜브 링크를 재생합니다.")
async def play(ctx, url):
    if ctx.author.voice is None:
        await ctx.send("먼저 음성 채널에 들어가 있어야 해요!")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    song_queue.append(url)
    await ctx.send(f"곡이 대기열에 추가되었습니다! 총 {len(song_queue)}곡 대기 중")
    if not ctx.voice_client.is_playing():
        play_next(ctx)

@bot.command(name="stop", help="현재 재생 중인 노래를 멈춥니다.")
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        song_queue.clear()
        await ctx.send("재생 중인 노래를 멈추고 대기열을 초기화했습니다!")
    else:
        await ctx.send("현재 재생 중인 노래가 없어요.")

@bot.command(name="skip", help="다음 노래로 넘어갑니다.")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("다음 노래로 넘어갑니다!")
    else:
        await ctx.send("재생 중인 노래가 없어서 스킵할 수 없어요.")

# ----------------------
# 메시지 이벤트
# ----------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 시참 메시지 처리
    if counting_active and TARGET_CHANNEL_ID and message.channel.id == TARGET_CHANNEL_ID:
        message_list.append(message)
        if len(message_list) % 4 == 0:
            await message.add_reaction("✅")
            reacted_messages.append(message)

    # ⚡ 반드시 커맨드 처리
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if TARGET_CHANNEL_ID and message.channel.id == TARGET_CHANNEL_ID:
        if message in message_list:
            message_list.remove(message)

#-------------------------
# 도움말
#-------------------------
@bot.command(name="help", help="사용 가능한 명령어를 표시합니다.")
async def help_command(ctx, command_name: str = None):
    if command_name:
        command = bot.get_command(command_name)
        if command and command.help:
            await ctx.send(f"**c!{command.name}** : {command.help}")
        else:
            await ctx.send(f"명령어 `{command_name}` 에 대한 설명이 없습니다.")
        return
    help_text = "**사용 가능한 명령어 목록**\n"
    for cmd in bot.commands:
        if not cmd.hidden and cmd.help:
            help_text += f"- `c!{cmd.name}` : {cmd.help}\n"
    await ctx.send(help_text)


# ----------------------
# 실행
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("토큰 없음")
else:
    bot.run(TOKEN)
