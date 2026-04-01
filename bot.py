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

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="c!", intents=intents, help_command=None)

CONFIG_FILE = "rino_config.json"
TARGET_COMMAND_CHANNEL_ID = None  # 일반 명령어용 채널
TARGET_COUNT_CHANNEL_ID = None    # 시참용 채널
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
# 설정 불러오기
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
# yt-dlp helper
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
        audio_url = info.get('url') or (info.get('formats')[0]['url'] if info.get('formats') else None)
        title = info.get('title', '알 수 없는 제목')
        return audio_url, title
    except Exception as e:
        print("yt-dlp error:", e)
        return None, None

# ----------------------
# 유튜브 영상 체크
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
            return {"title": title, "url": f"https://youtu.be/{video_id}"}
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
# 명령어 채널 설정
# ----------------------
@bot.command(name="명령어채널설정")
async def 명령어채널설정(ctx, *, channel_name):
    global TARGET_COMMAND_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send(f"'{channel_name}' 채널을 찾을 수 없습니다.")
        return
    TARGET_COMMAND_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"명령어 채널이 <#{TARGET_COMMAND_CHANNEL_ID}> 로 설정되었습니다!")

# ----------------------
# 시참 채널 설정
# ----------------------
@bot.command(name="시참채널설정")
async def 시참채널설정(ctx, *, channel_name):
    global TARGET_COUNT_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send(f"'{channel_name}' 채널을 찾을 수 없습니다.")
        return
    TARGET_COUNT_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"시참 채널이 <#{TARGET_COUNT_CHANNEL_ID}> 로 설정되었습니다!")

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
        await ctx.send(f"✅ 설정 완료!\n채널 ID: {channel_id}")
    else:
        await ctx.send("❌ 채널 ID 추출 실패... 링크를 다시 확인해주세요.")

# ----------------------
# 유튜브 알림 채널
# ----------------------
@bot.command(name="유튜브알림채널설정")
async def 유튜브알림채널설정(ctx, *, channel_name):
    global YOUTUBE_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send("채널을 찾을 수 없습니다.")
        return
    YOUTUBE_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"유튜브 알림 채널이 {channel.mention} 로 설정되었습니다!")

# ----------------------
# 시참 시작/종료
# ----------------------
@bot.command(name="시참시작")
async def start_count(ctx):
    global counting_active, message_list, reacted_messages
    if TARGET_COUNT_CHANNEL_ID is None:
        await ctx.send("먼저 시참 채널을 설정해주세요.")
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
# 시참 메시지 감지
# ----------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 시참용
    if counting_active and TARGET_COUNT_CHANNEL_ID and message.channel.id == TARGET_COUNT_CHANNEL_ID:
        message_list.append(message)
        if len(message_list) % 4 == 0:
            await message.add_reaction("✅")
            reacted_messages.append(message)

    # 명령어용 채널 제한
    if TARGET_COMMAND_CHANNEL_ID and message.channel.id != TARGET_COMMAND_CHANNEL_ID:
        return

    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if TARGET_COUNT_CHANNEL_ID and message.channel.id == TARGET_COUNT_CHANNEL_ID:
        if message in message_list:
            message_list.remove(message)

# ----------------------
# 유튜브 자동 체크 루프
# ----------------------
async def youtube_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        data = check_youtube()
        if data and YOUTUBE_CHANNEL_ID:
            channel = bot.get_channel(YOUTUBE_CHANNEL_ID)
            if channel:
                await channel.send(f"📢 새 영상 업로드!\n**{data['title']}**\n{data['url']}")
        await asyncio.sleep(60)

# ----------------------
# 채널 ID 추출
# ----------------------
def get_channel_id_from_url(url):
    try:
        res = requests.get(url)
        html = res.text
        match = re.search(r'"channelId":"(UC[\w-]+)"', html)
        if match:
            return match.group(1)
    except Exception as e:
        print("채널 ID 추출 실패:", e)
    return None

# ----------------------
# 토큰 실행
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("토큰 없음")
else:
    bot.run(TOKEN)
