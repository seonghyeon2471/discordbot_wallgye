import discord
from discord.ext import commands
from discord.utils import get
import json
import os
import subprocess
from discord import FFmpegPCMAudio
import requests
import xml.etree.ElementTree as ET
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="c!", intents=intents, help_command=None)

CONFIG_FILE = "rino_config.json"
TARGET_CHANNEL_ID = None
TARGET_YOUTUBE_LINK = None
TARGET_STREAM_PLAN = None
TARGET_YOUTUBE_CHANNEL_ID = None
LAST_VIDEO_ID = None
YOUTUBE_CHANNEL_ID = None
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
        TARGET_YOUTUBE_CHANNEL_ID = data.get("TARGET_YOUTUBE_CHANNEL_ID")
        YOUTUBE_CHANNEL_ID = data.get("YOUTUBE_CHANNEL_ID")
        LAST_VIDEO_ID = data.get("LAST_VIDEO_ID")

# ----------------------
# 설정 저장 함수
# ----------------------
def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "TARGET_CHANNEL_ID": TARGET_CHANNEL_ID,
            "TARGET_YOUTUBE_LINK": TARGET_YOUTUBE_LINK,
            "TARGET_STREAM_PLAN": TARGET_STREAM_PLAN,
            "TARGET_YOUTUBE_CHANNEL_ID": TARGET_YOUTUBE_CHANNEL_ID,
            "YOUTUBE_CHANNEL_ID": YOUTUBE_CHANNEL_ID,
            "LAST_VIDEO_ID": LAST_VIDEO_ID
        }, f)

# ----------------------
# yt-dlp nightly helper
# ----------------------
def get_audio_url(url):
    try:
        result = subprocess.run(
            ["./yt-dlp", "-j", "-f", "bestaudio", "--cookies", "cookies.txt", url],
            capture_output=True,
            text=True
        )

        print("===== yt-dlp stdout =====")
        print(result.stdout[:1000])  # 너무 길어서 1000자만
        print("===== yt-dlp stderr =====")
        print(result.stderr)

        if not result.stdout.strip():
            return None, None

        info = json.loads(result.stdout)

        audio_url = info.get('url') or (info.get('formats')[0]['url'] if info.get('formats') else None)
        title = info.get('title', '알 수 없는 제목')

        print("audio_url:", audio_url)

        return audio_url, title

    except Exception as e:
        print("yt-dlp error:", e)
        return None, None

# ----------------------
# 유튜브 영상 업로드 체크
# ----------------------
def check_youtube():
    global LAST_VIDEO_ID

    if not TARGET_YOUTUBE_CHANNEL_ID:
        return None

    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={TARGET_YOUTUBE_CHANNEL_ID}"

    try:
        res = requests.get(url)
        root = ET.fromstring(res.text)

        namespace = {"yt": "http://www.youtube.com/xml/schemas/2015"}

        entry = root.find("entry")
        if entry is None:
            return None

        video_id = entry.find("yt:videoId", namespace).text
        title = entry.find("title").text

        if LAST_VIDEO_ID != video_id:
            LAST_VIDEO_ID = video_id
            save_config()

            return {
                "title": title,
                "url": f"https://youtu.be/{video_id}"
            }

    except Exception as e:
        print("유튜브 체크 오류:", e)

    return None

# ----------------------
# 이벤트
# ----------------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    bot.loop.create_task(youtube_loop())

# ----------------------
# 명령어
# ----------------------
@bot.command(name="채널설정")  # help="사용할 채널을 설정합니다."
async def 채널설정(ctx, *, channel_name):
    global TARGET_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send(f"'{channel_name}' 채널을 찾을 수 없습니다.")
        return
    TARGET_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"채널이 <#{TARGET_CHANNEL_ID}> 로 설정되었습니다!")

@bot.command(name="유튜브알림채널설정")  # help="유튜브 알림 채널을 설정합니다"
async def 유튜브알림채널설정(ctx, *, channel_name):
    global YOUTUBE_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)

    if channel is None:
        await ctx.send("채널을 찾을 수 없습니다.")
        return

    YOUTUBE_CHANNEL_ID = channel.id
    save_config()

    await ctx.send(f"유튜브 알림 채널이 {channel.mention} 로 설정되었습니다!")

@bot.command(name="유튜브설정")
async def 유튜브설정(ctx, *, youtube_link):
    global TARGET_YOUTUBE_LINK, TARGET_YOUTUBE_CHANNEL_ID

    TARGET_YOUTUBE_LINK = youtube_link

    # 🔥 채널 ID 자동 추출
    channel_id = get_channel_id_from_url(youtube_link)

    if channel_id:
        TARGET_YOUTUBE_CHANNEL_ID = channel_id
        save_config()
        await ctx.send(f"✅ 설정 완료!\n채널 ID: {channel_id}")
    else:
        await ctx.send("❌ 채널 ID 추출 실패... 링크를 다시 확인해주세요.")

@bot.command(name="유튜브", help="유튜브 채널을 보여줍니다.")
async def 유튜브(ctx):
    if TARGET_YOUTUBE_LINK:
        await ctx.send(TARGET_YOUTUBE_LINK)
    else:
        await ctx.send("유튜브 링크가 설정되지 않았습니다.")

@bot.command(name="유튜브채널설정")
async def 유튜브채널설정(ctx, channel_id: str):
    global TARGET_YOUTUBE_CHANNEL_ID

    TARGET_YOUTUBE_CHANNEL_ID = channel_id
    save_config()

    await ctx.send(f"유튜브 채널 ID 설정 완료: {channel_id}")

# ----------------------
# 유튜브 자동 감지 루프
# ----------------------
async def youtube_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        data = check_youtube()

        if data and YOUTUBE_CHANNEL_ID:
            channel = bot.get_channel(TARGET_CHANNEL_ID)

            if channel:
                await channel.send(
                    f"📢 새 영상 업로드!\n"
                    f"**{data['title']}**\n"
                    f"{data['url']}"
                )

        await asyncio.sleep(60)  # 1분마다 체크

# ----------------------
# 채널 ID 추가
# ----------------------
def get_channel_id_from_url(url):
    try:
        res = requests.get(url)
        html = res.text

        # ytInitialData에서 channelId 찾기
        import re
        match = re.search(r'"channelId":"(UC[\w-]+)"', html)

        if match:
            return match.group(1)

    except Exception as e:
        print("채널 ID 추출 실패:", e)

    return None

@bot.command(name="방송일정설정") # help="방송 일정을 설정합니다."
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

@bot.command(name="시참시작") # help="시참 받기를 시작합니다."
async def start_count(ctx):
    global counting_active, message_list, reacted_messages
    if TARGET_CHANNEL_ID is None:
        await ctx.send("먼저 채널 설정해주세요.")
        return
    counting_active = True
    message_list = []
    reacted_messages = []
    await ctx.send("시참 시작!")

@bot.command(name="시참끝") # help="시참 받기를 종료합니다."
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
# 유튜브 대기열 + 제어    -> 사용 안함 노래재생
# ----------------------
def play_next(ctx):
    if len(song_queue) == 0:
        return

    url = song_queue.pop(0)
    audio_url, title = get_audio_url(url)

    if not audio_url:
        bot.loop.create_task(ctx.send("❌ 재생 실패, 다음 곡으로 넘어갑니다."))
        play_next(ctx)
        return

    ctx.voice_client.stop()
    ctx.voice_client.play(
        FFmpegPCMAudio(
            audio_url,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        ),
        after=lambda e: play_next(ctx)
    )
    bot.loop.create_task(ctx.send(f"🎵 {title} 재생 시작!"))

@bot.command(name="play")
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

@bot.command(name="stop")
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        song_queue.clear()
        await ctx.send("재생 중인 노래를 멈추고 대기열을 초기화했습니다!")
    else:
        await ctx.send("현재 재생 중인 노래가 없어요.")

@bot.command(name="skip")
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

    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if TARGET_CHANNEL_ID and message.channel.id == TARGET_CHANNEL_ID:
        if message in message_list:
            message_list.remove(message)

# ----------------------
# 도움말
# ----------------------
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
