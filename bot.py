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
import re
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="c!", intents=intents, help_command=None)

# ----------------------
# 채널 / 설정 변수
# ----------------------
CONFIG_FILE = "rino_config.json"

TARGET_COMMAND_CHANNEL_ID = None   # 명령어 채널
TARGET_COUNT_CHANNEL_ID = None     # 시참 채널

TARGET_YOUTUBE_LINK = None
TARGET_STREAM_PLAN = None
TARGET_YOUTUBE_CHANNEL_ID = None
YOUTUBE_CHANNEL_ID = None
LAST_VIDEO_ID = None

counting_active = False

message_list = []
reacted_messages = []
song_queue = []

# ----------------------
# 설정 로드
# ----------------------
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        TARGET_COMMAND_CHANNEL_ID = data.get("TARGET_COMMAND_CHANNEL_ID")
        TARGET_COUNT_CHANNEL_ID = data.get("TARGET_COUNT_CHANNEL_ID")
        TARGET_YOUTUBE_LINK = data.get("TARGET_YOUTUBE_LINK")
        TARGET_STREAM_PLAN = data.get("TARGET_STREAM_PLAN")
        TARGET_YOUTUBE_CHANNEL_ID = data.get("TARGET_YOUTUBE_CHANNEL_ID")
        YOUTUBE_CHANNEL_ID = data.get("YOUTUBE_CHANNEL_ID")
        LAST_VIDEO_ID = data.get("LAST_VIDEO_ID")

# ----------------------
# 설정 저장
# ----------------------
def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "TARGET_COMMAND_CHANNEL_ID": TARGET_COMMAND_CHANNEL_ID,
            "TARGET_COUNT_CHANNEL_ID": TARGET_COUNT_CHANNEL_ID,
            "TARGET_YOUTUBE_LINK": TARGET_YOUTUBE_LINK,
            "TARGET_STREAM_PLAN": TARGET_STREAM_PLAN,
            "TARGET_YOUTUBE_CHANNEL_ID": TARGET_YOUTUBE_CHANNEL_ID,
            "YOUTUBE_CHANNEL_ID": YOUTUBE_CHANNEL_ID,
            "LAST_VIDEO_ID": LAST_VIDEO_ID
        }, f)

# ----------------------
# yt-dlp
# ----------------------
def get_audio_url(url):
    try:
        result = subprocess.run(
            ["./yt-dlp", "-j", "-f", "bestaudio", "--cookies", "cookies.txt", url],
            capture_output=True,
            text=True
        )

        if not result.stdout.strip():
            return None, None

        info = json.loads(result.stdout)

        audio_url = info.get("url") or (
            info.get("formats")[0]["url"] if info.get("formats") else None
        )
        title = info.get("title", "알 수 없는 제목")

        return audio_url, title

    except Exception as e:
        print("yt-dlp error:", e)
        return None, None

# ----------------------
# 유튜브 체크
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
# 유튜브 루프
# ----------------------
async def youtube_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        data = check_youtube()

        if data and YOUTUBE_CHANNEL_ID:
            channel = bot.get_channel(YOUTUBE_CHANNEL_ID)
            if channel:
                await channel.send(
                    f"📢 새 영상 업로드!\n"
                    f"**{data['title']}**\n"
                    f"{data['url']}"
                )

        await asyncio.sleep(60)

# ----------------------
# 채널 ID 추출
# ----------------------
def get_channel_id_from_url(url):
    """
    유튜브 @닉네임 URL에서 채널 ID(UC...) 추출
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        html = res.text

        # channelId를 찾는 안전한 정규식 (ytInitialData 또는 meta tag 활용)
        match = re.search(r'"channelId":"(UC[\w-]{22})"', html)
        if match:
            return match.group(1)

        # fallback: canonical link에 /channel/가 있으면
        match2 = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', html)
        if match2:
            return match2.group(1)

    except Exception as e:
        print("채널 ID 추출 실패:", e)

    return None

# ----------------------
# READY
# ----------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(youtube_loop())

# ----------------------
# 채널 설정
# ----------------------
@bot.command(name="명령어채널설정")
async def 명령어채널설정(ctx, *, channel_name):
    global TARGET_COMMAND_CHANNEL_ID

    channel = get(ctx.guild.channels, name=channel_name)
    if not channel:
        await ctx.send("채널 없음")
        return

    TARGET_COMMAND_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"명령어 채널 설정 완료: <#{channel.id}>")

@bot.command(name="시참채널설정")
async def 시참채널설정(ctx, *, channel_name):
    global TARGET_COUNT_CHANNEL_ID

    channel = get(ctx.guild.channels, name=channel_name)
    if not channel:
        await ctx.send("채널 없음")
        return

    TARGET_COUNT_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"시참 채널 설정 완료: <#{channel.id}>")

# ----------------------
# 유튜브 설정
# ----------------------
@bot.command(name="유튜브설정")
async def 유튜브설정(ctx, *, youtube_link):
    global TARGET_YOUTUBE_LINK, TARGET_YOUTUBE_CHANNEL_ID

    TARGET_YOUTUBE_LINK = youtube_link

    channel_id = get_channel_id_from_url(youtube_link)

    if channel_id:
        TARGET_YOUTUBE_CHANNEL_ID = channel_id
        save_config()
        await ctx.send(f"설정 완료: {channel_id}")
    else:
        await ctx.send("채널 ID 추출 실패")

@bot.command(name="유튜브알림채널설정")
async def 유튜브알림채널설정(ctx, *, channel_name):
    global YOUTUBE_CHANNEL_ID

    channel = get(ctx.guild.channels, name=channel_name)
    if not channel:
        await ctx.send("채널 없음")
        return

    YOUTUBE_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"알림 채널 설정 완료: {channel.mention}")

# ----------------------
# 시참 기능
# ----------------------
@bot.command(name="시참시작")
async def start_count(ctx):
    global counting_active, message_list, reacted_messages

    if not TARGET_COUNT_CHANNEL_ID:
        await ctx.send("시참 채널 먼저 설정")
        return

    counting_active = True
    message_list = []
    reacted_messages = []
    await ctx.send("시참 시작!")

@bot.command(name="시참끝")
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

    # 시참
    if counting_active and TARGET_COUNT_CHANNEL_ID and message.channel.id == TARGET_COUNT_CHANNEL_ID:
        message_list.append(message)

        if len(message_list) % 4 == 0:
            await message.add_reaction("✅")
            reacted_messages.append(message)

    # 명령어 채널 제한
    if TARGET_COMMAND_CHANNEL_ID and message.channel.id != TARGET_COMMAND_CHANNEL_ID:
        return

    await bot.process_commands(message)

# ----------------------
# 음성채널
# ----------------------
@bot.command(name="join", help="봇을 음성채팅으로 데려오기!")
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("음성채널 들어가")
        return

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()

    await ctx.send("입장 완료")

@bot.command(name="exit", help="봇을 음성채팅에서 내보내기!")
async def exit(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("퇴장 완료")

# ----------------------
# 유튜브 링크 출력
# ----------------------
@bot.command(name="유튜브", help="유튜브 채널 링크 불러오기!")
async def 유튜브(ctx):
    if TARGET_YOUTUBE_LINK:
        await ctx.send(TARGET_YOUTUBE_LINK)
    else:
        await ctx.send("없음")

# ----------------------
# 방송 일정
# ----------------------
@bot.command(name="방송일정설정")
async def 방송일정설정(ctx, *, plan):
    global TARGET_STREAM_PLAN
    TARGET_STREAM_PLAN = plan
    save_config()
    await ctx.send("저장 완료")

@bot.command(name="방송일정", help="방송 일정 확인하기!")
async def 방송일정(ctx):
    await ctx.send(TARGET_STREAM_PLAN or "없음")

# ----------------------
# help
# ----------------------
@bot.command(name="help", help="도움말 확인하기!")
async def help_command(ctx, cmd=None):
    if cmd:
        command = bot.get_command(cmd)
        if command:
            await ctx.send(f"c!{command.name} : {command.help}")
        else:
            await ctx.send("없음")
        return

    text = "명령어 목록:\n"
    for c in bot.commands:
        text += f"- c!{c.name}\n"

    await ctx.send(text)

# ----------------------
# 실행
# ----------------------
TOKEN = os.getenv("DISCORD_WALLTOKEN")

if TOKEN:
    bot.run(TOKEN)
else:
    print("토큰 없음")
