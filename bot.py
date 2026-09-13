import asyncio
import http.server
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import discord
from discord.ext import commands
import yt_dlp

# ==========================================
# 1. WEB SERVER MINI CHỐNG RENDER NGỦ (SPIN DOWN)
# ==========================================


class MyHandler(http.server.SimpleHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b'Bot is alive and running!')


def run_web():
  server_address = ('0.0.0.0', 10000)
  httpd = http.server.HTTPServer(server_address, MyHandler)
  httpd.serve_forever()


t = threading.Thread(target=run_web)
t.daemon = True
t.start()

# ==========================================
# 2. CẤU HÌNH BOT VÀ INTENTS
# ==========================================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 3. CẤU HÌNH YT-DLP VÀ FFMPEG
# ==========================================

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'scsearch',
    'quiet': True,
    'extract_flat': False,
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn -bufsize 64k',
}

# ==========================================
# 4. QUẢN LÝ HÀNG ĐỢI VÀ TRẠNG THÁI NHẠC
# ==========================================

music_queues = {}
music_loops = {}
current_songs = {}


def play_next(ctx):
  guild_id = ctx.guild.id

  if (
      guild_id in music_loops
      and music_loops[guild_id]
      and guild_id in current_songs
  ):
    song = current_songs[guild_id]
  elif guild_id in music_queues and len(music_queues[guild_id]) > 0:
    song = music_queues[guild_id].pop(0)
    current_songs[guild_id] = song
  else:
    asyncio.run_coroutine_threadsafe(discon(ctx), bot.loop)
    return

  player = discord.FFmpegPCMAudio(song['url'], **ffmpeg_options)
  ctx.voice_client.play(
      player,
      after=lambda e: asyncio.run_coroutine_threadsafe(
          play_next_async(ctx), bot.loop
      ),
  )
  asyncio.run_coroutine_threadsafe(
      ctx.send(f'🎶 Đang phát: **{song["title"]}**'), bot.loop
  )


async def play_next_async(ctx):
  play_next(ctx)


async def discon(ctx):
  await asyncio.sleep(60)
  if ctx.voice_client and not ctx.voice_client.is_playing():
    await ctx.voice_client.disconnect()


# ==========================================
# 5. SỰ KIỆN KHI BOT SẴN SÀNG
# ==========================================


@bot.event
async def on_ready():
  print(f'Bot đã đăng nhập thành công dưới tên {bot.user}')


# ==========================================
# 6. CÁC LỆNH PHÁT NHẠC VÀ QUẢN LÝ
# ==========================================


@bot.command(name='phat')
async def play(ctx, *, search: str):
  if not ctx.author.voice:
    await ctx.send('⚠️ Bạn phải vào một phòng Voice trước đã nhé!')
    return

  if 'youtube.com' in search or 'youtu.be' in search:
    await ctx.send(
        '⚠️ Do YouTube chặn link trực tiếp trên server, bạn hãy gõ **tên bài'
        ' hát** hoặc dùng link **SoundCloud** nhé!'
    )
    return

  channel = ctx.author.voice.channel
  if not ctx.voice_client:
    await channel.connect()

  async with ctx.typing():
    loop = asyncio.get_event_loop()
    try:
      data = await loop.run_in_executor(
          None, lambda: ytdl.extract_info(search, download=False)
      )
    except Exception as e:
      await ctx.send(f'⚠️ Không thể tìm thấy bài hát: {e}')
      return

    if not data:
      await ctx.send('❌ Không tìm thấy kết quả nào phù hợp!')
      return

    if 'entries' in data:
      data = data['entries'][0]

    song = {'title': data.get('title', search), 'url': data['url']}
    guild_id = ctx.guild.id

    if ctx.voice_client.is_playing():
      if guild_id not in music_queues:
        music_queues[guild_id] = []
      music_queues[guild_id].append(song)
      await ctx.send(
          f'📥 Đã thêm vào hàng đợi: **{song["title"]}** (Vị trí:'
          f' {len(music_queues[guild_id])})'
      )
    else:
      current_songs[guild_id] = song
      player = discord.FFmpegPCMAudio(song['url'], **ffmpeg_options)
      ctx.voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next_async(ctx), bot.loop
          ),
      )
      await ctx.send(f'🎶 Đang phát: **{song["title"]}**')


@bot.command(name='skip')
async def skip(ctx):
  if ctx.voice_client and ctx.voice_client.is_playing():
    ctx.voice_client.stop()
    await ctx.send('⏭️ Đã bỏ qua bài hiện tại!')
  else:
    await ctx.send('⚠️ Bot hiện không phát bài nào cả.')


@bot.command(name='list')
async def show_query(ctx):
  guild_id = ctx.guild.id
  if guild_id not in music_queues or len(music_queues[guild_id]) == 0:
    await ctx.send('📭 Hàng đợi hiện đang trống!')
  else:
    queue_list = ''
    for i, song in enumerate(music_queues[guild_id], start=1):
      queue_list += f'`{i}.` {song["title"]}\n'

    embed = discord.Embed(
        title='🎶 Danh sách hàng đợi',
        description=queue_list,
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)


@bot.command(name='lap')
async def toggle_loop(ctx):
  guild_id = ctx.guild.id
  if guild_id not in music_loops:
    music_loops[guild_id] = False

  music_loops[guild_id] = not music_loops[guild_id]
  status = 'BẬT 🔂' if music_loops[guild_id] else 'TẮT ➡️'
  await ctx.send(f'🔄 Chế độ lặp lại bài hát hiện tại đã: **{status}**')


@bot.command(name='loi')
async def lyrics(ctx, *, query: str = None):
  guild_id = ctx.guild.id

  if not query:
    if guild_id in current_songs:
      query = current_songs[guild_id]['title']
    else:
      await ctx.send(
          '⚠️ Bot không phát bài nào cả! Hãy gõ tên bài, tên ca sĩ hoặc từ khóa'
          ' nhé (Ví dụ: `!loi Sơn Tùng`)'
      )
      return

  async with ctx.typing():
    try:
      search_query = query

      # Nếu là link YouTube, dùng Noembed lấy tiêu đề
      if 'youtube.com' in query or 'youtu.be' in query:
        try:
          api_url = f'https://noembed.com/embed?url={query}'
          req = urllib.request.Request(
              api_url, headers={'User-Agent': 'Mozilla/5.0'}
          )
          with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if 'title' in data:
              raw_title = data['title']

              # Dùng Regex lột sạch mấy từ thừa như [Official MV], (Audio), ft, ... cho sạch sẽ
              cleaned_title = re.sub(
                  r'(?i)\b(official\s*(music\s*)?video|official\s*audio|official\s*lyric\s*video|mv|audio|lyric(s)?|ft\.?|feat\.?|live)\b',
                  '',
                  raw_title,
              )
              # Xóa bỏ các cặp ngoặc vuông/tròn thừa còn sót lại sau khi cắt
              cleaned_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', cleaned_title)
              # Gom lại khoảng trắng cho gọn
              search_query = ' '.join(cleaned_title.split())

              # Nếu lỡ tay lọc quá đà mà trống trơn thì quay về dùng lại tên gốc của Noembed
              if not search_query.strip():
                search_query = raw_title
        except Exception as e:
          print(f'Lỗi lấy tiêu đề qua API: {e}')

      # Tìm kiếm lời bài hát qua API lrclib với từ khóa đã được gọt giũa sạch sẽ
      encoded_query = urllib.parse.quote(search_query)
      url = f'https://lrclib.net/api/search?q={encoded_query}'
      req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
      with urllib.request.urlopen(req) as response:
        result_data = json.loads(response.read().decode())

      if not result_data:
        await ctx.send(
            f'❌ Không tìm thấy lời cho từ khóa: **{search_query}**'
        )
        return

      track = None
      for item in result_data:
        if item.get('plainLyrics'):
          track = item
          break

      if not track:
        track = result_data[0]

      lyric_text = track.get('plainLyrics') or 'Không có sẵn lời cho bài này.'
      title = track.get('trackName', search_query)
      artist = track.get('artistName', 'Unknown')

      if len(lyric_text) > 4000:
        lyric_text = lyric_text[:4000] + '\n...(Lời quá dài bị cắt bớt)'

      embed = discord.Embed(
          title=f'🎤 Lời bài hát: {title} - {artist}',
          description=lyric_text,
          color=discord.Color.green(),
      )
      await ctx.send(embed=embed)
    except Exception as e:
      await ctx.send(f'⚠️ Có lỗi xảy ra khi lấy lời bài hát: {e}')

@bot.command(name='dung')
async def stop(ctx):
  guild_id = ctx.guild.id
  if guild_id in music_queues:
    music_queues[guild_id].clear()
  if guild_id in music_loops:
    music_loops[guild_id] = False
  if ctx.voice_client:
    await ctx.voice_client.disconnect()
    await ctx.send(
        '🛑 Đã dừng nhạc, xóa hàng đợi và ngắt kết nối khỏi phòng thoại!'
    )


# ==========================================
# 7. KHỞI CHẠY BOT VỚI TOKEN TỪ RENDER
# ==========================================

token = os.getenv('DISCORD_TOKEN')

if not token:
  print(
      '⚠️ LỖI CHƯA CÓ TOKEN: Hãy cấu hình biến DISCORD_TOKEN trên Render nhé!'
  )
else:
  bot.run(token)
