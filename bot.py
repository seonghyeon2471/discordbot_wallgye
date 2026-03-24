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
# 설정 저장
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
# 기본 명령어
# ----------------------
@bot.command(name="채널설정")
async def 채널설정(ctx, *, channel_name):
    global TARGET_CHANNEL_ID
    channel = get(ctx.guild.channels, name=channel_name)
    if channel is None:
        await ctx.send(f"'{channel_name}' 채널을 찾을 수 없습니다.")
        return
    TARGET_CHANNEL_ID = channel.id
    save_config()
    await ctx.send(f"채널이 <#{TARGET_CHANNEL_ID}> 로 설정되었습니다!")

@bot.command(name="유튜브설정")
async def 유튜브설정(ctx, *, youtube_link):
    global TARGET_YOUTUBE_LINK
    TARGET_YOUTUBE_LINK = youtube_link
    save_config()
    await ctx.send("유튜브 링크 설정 완료!")

@bot.command(name="유튜브")
async def 유튜브(ctx):
    await ctx.send(TARGET_YOUTUBE_LINK or "유튜브 링크가 설정되지 않았습니다.")

@bot.command(name="방송일정설정")
async def 방송일정설정(ctx, *, stream_plan):
    global TARGET_STREAM_PLAN
    TARGET_STREAM_PLAN = stream_plan
    save_config()
    await ctx.send("방송 일정 설정 완료!")

@bot.command(name="방송일정")
async def 방송일정(ctx):
    await ctx.send(TARGET_STREAM_PLAN or "방송 일정이 없습니다.")

# ----------------------
# 시참 기능
# ----------------------
@bot.command(name="시참시작")
async def start_count(ctx):
    global counting_active, message_list, reacted_messages
    if TARGET_CHANNEL_ID is None:
        await ctx.send("먼저 채널 설정해주세요.")
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
# 음성 채널
# ----------------------
@bot.command(name="join")
async def join_voice(ctx):
    if ctx.author.voice is None:
        await ctx.send("먼저 음성 채널에 들어가 있어야 합니다!")
        return

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()

    await ctx.send(f"{channel.name} 채널로 들어왔어요!")

@bot.command(name="exit")
async def leave_voice(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("음성 채널에서 나왔어요!")
    else:
        await ctx.send("저는 현재 음성 채널에 없어요.")

# ----------------------
# 🎵 유튜브 재생 핵심
# ----------------------
def play_next(ctx):
    if not song_queue:
        return

    url = song_queue.pop(0)

    ydl_opts = {
        'format': 'bestaudio/best/bestaudio*',
        'format_sort': ['abr', 'asr'],
        'noplaylist': True,
        'quiet': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'cookiefile': 'cookies.txt',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        bot.loop.create_task(ctx.send("❌ 영상 정보를 가져오지 못했습니다. 다음 곡으로 넘어갑니다."))
        play_next(ctx)
        return

    if info is None:
        bot.loop.create_task(ctx.send("❌ 재생 불가 영상입니다."))
        play_next(ctx)
        return

    if 'entries' in info:
        info = info['entries'][0]
        if info is None:
            play_next(ctx)
            return

    audio_url = info.get('url') or info['formats'][0]['url']
    if not audio_url:
        bot.loop.create_task(ctx.send("❌ 오디오 URL을 못 가져왔습니다."))
        play_next(ctx)
        return

    ctx.voice_client.stop()

    source = FFmpegPCMAudio(
        audio_url,
        before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_on_network_error 1',
        options='-vn'
    )

    ctx.voice_client.play(source, after=lambda e: play_next(ctx))

    title = info.get('title', '알 수 없는 제목')
    bot.loop.create_task(ctx.send(f"🎵 {title} 재생 시작!"))

# ----------------------
# 🎵 명령어
# ----------------------
@bot.command(name="play")
async def play(ctx, *, url):
    if ctx.author.voice is None:
        await ctx.send("먼저 음성 채널에 들어가 있어야 해요!")
        return

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    song_queue.append(url)
    await ctx.send(f"대기열 추가! ({len(song_queue)}곡)")

    if not ctx.voice_client.is_playing():
        play_next(ctx)

@bot.command(name="skip")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ 스킵!")
    else:
        await ctx.send("재생 중인 곡이 없습니다.")

@bot.command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        song_queue.clear()
        await ctx.send("⏹ 정지 & 대기열 초기화!")
    else:
        await ctx.send("재생 중이 아닙니다.")

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
# help
# ----------------------
@bot.command(name="help")
async def help_command(ctx, command_name: str = None):
    if command_name:
        command = bot.get_command(command_name)
        if command and command.help:
            await ctx.send(f"c!{command.name} : {command.help}")
        else:
            await ctx.send("설명 없음")
        return

    msg = "**명령어 목록**\n"
    for cmd in bot.commands:
        if not cmd.hidden:
            msg += f"- c!{cmd.name}\n"

    await ctx.send(msg)

# ----------------------
# 실행
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("토큰 없음")
else:
    bot.run(TOKEN)
