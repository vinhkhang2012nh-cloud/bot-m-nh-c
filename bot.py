import asyncio
import http.server
import json
import os
import threading
import urllib.parse
import urllib.request
import discord
from discord.ext import commands
import yt_dlp

# --- WEB SERVER MINI ĐỂ CHỐNG RENDER NGỦ (SPIN DOWN) ---


class MyHandler(http.server.SimpleHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b'Bot is alive and running!')


def run_web():
  server_address = ('0.0.0.0', 10000)
  httpd = http.server.HTTPServer(server_address, MyHandler)
  httpd.serve_forever()


# Chạy web server ở một luồng riêng biệt
t = threading.Thread(target=run_web)
t.daemon = True
t.start()
# -----------------------------------------------------

# Cấu hình Intents cho Bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Cấu hình yt-dlp (dùng scsearch để tối ưu, không sợ bị chặn)
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'scsearch',
    'quiet': True,
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Cấu hình FFmpeg để chống giật mạng
ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn -bufsize 64k',
}

# Quản lý hàng đợi, trạng thái lặp và bài hát hiện tại cho từng server
music_queues = {}
music_loops = {}
current_songs = {}


def play_next(ctx):
  guild_id = ctx.guild.id

  # Kiểm tra nếu bật chế độ lặp lại bài hiện tại
  if (
      guild_id in music_loops
      and music_loops[guild_id]
      and guild_id in current_songs
  ):
    song = current_songs[guild_id]
  elif guild_id in music_queues and len(music_queues[guild_id]) > 0:
    # Lấy bài tiếp theo trong hàng đợi
    song = music_queues[guild_id].pop(0)
    current_songs[guild_id] = song
  else:
    # Hết hàng đợi và không lặp -> Chờ một lúc rồi rời phòng
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
  await asyncio.sleep(60)  # Đợi 1 phút nếu không có ai gọi thì out voice
  if ctx.voice_client and not ctx.voice_client.is_playing():
    await ctx.voice_client.disconnect()


@bot.event
async def on_ready():
  print(f'Bot đã đăng nhập thành công dưới tên {bot.user}')


@bot.command(name='phat')
async def play(ctx, *, search: str):
  if not ctx.author.voice:
    await ctx.send('⚠️ Bạn phải vào một phòng Voice trước đã nhé!')
    return

  channel = ctx.author.voice.channel
  if not ctx.voice_client:
    await channel.connect()

  async with ctx.typing():
    # Trích xuất thông tin bài hát từ từ khóa tìm kiếm
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(search, download=False)
    )
    if 'entries' in data:
      data = data['entries'][0]

    song = {'title': data['title'], 'url': data['url']}
    guild_id = ctx.guild.id

    # Nếu bot đang bận phát nhạc bài khác -> Cho vào hàng đợi
    if ctx.voice_client.is_playing():
      if guild_id not in music_queues:
        music_queues[guild_id] = []
      music_queues[guild_id].append(song)
      await ctx.send(
          f'📥 Đã thêm vào hàng đợi: **{song["title"]}** (Vị trí:'
          f' {len(music_queues[guild_id])})'
      )
    else:
      # Nếu bot đang rảnh -> Phát luôn
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
    ctx.voice_client.stop()  # Dừng bài hiện tại, hàm after tự động gọi bài tiếp
    await ctx.send('⏭️ Đã bỏ qua bài hiện tại!')
  else:
    await ctx.send('⚠️ Bot hiện không phát bài nào cả.')


@bot.command(name='list')
async def show_queue(ctx):
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
  if not query:
    guild_id = ctx.guild.id
    if guild_id in current_songs:
      query = current_songs[guild_id]['title']
    else:
      await ctx.send(
          '⚠️ Bot không phát bài nào và bạn cũng không nhập tên bài hát cần tìm!'
      )
      return

  async with ctx.typing():
    try:
      encoded_query = urllib.parse.quote(query)
      url = f'https://lrclib.net/api/search?q={encoded_query}'
      req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
      with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())

      if not data:
        await ctx.send(f'❌ Không tìm thấy lời cho bài: **{query}**')
        return

      track = data[0]
      lyric_text = track.get('plainLyrics') or 'Không có sẵn lời cho bài này.'
      title = track.get('trackName', query)
      artist = track.get('artistName', 'Unknown')

      # Giới hạn kí tự của Discord Embed (tối đa 4000 kí tự mô tả)
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


# Lấy token từ biến môi trường trên Render
token = os.getenv('DISCORD_TOKEN')

if not token:
  print(
      '⚠️ LỖI CHƯA CÓ TOKEN: Bạn hãy tạo biến DISCORD_TOKEN trong phần'
      ' Environment của Render nhé!'
  )
else:
  bot.run(token)
