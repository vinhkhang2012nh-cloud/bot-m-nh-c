import asyncio
import discord
from discord.ext import commands
import yt_dlp

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


# Quản lý hàng đợi cho từng server (Guild ID -> List chứa các bài hát)
music_queues = {}


def play_next(ctx):
  guild_id = ctx.guild.id
  if guild_id in music_queues and len(music_queues[guild_id]) > 0:
    # Lấy bài tiếp theo trong hàng đợi
    next_song = music_queues[guild_id].pop(0)
    player = discord.FFmpegPCMAudio(next_song['url'], **ffmpeg_options)

    # Dùng lambda để truyền ctx vào play_next khi bài này kết thúc
    ctx.voice_client.play(
        player,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next_async(ctx), bot.loop
        ),
    )
    # Gửi thông báo đang phát bài mới
    asyncio.run_coroutine_threadsafe(
        ctx.send(f'🎶 Đang phát tiếp: **{next_song["title"]}**'), bot.loop
    )
  else:
    # Hết hàng đợi thì để một lúc rồi rời phòng
    asyncio.run_coroutine_threadsafe(discon(ctx), bot.loop)


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
    ctx.voice_client.stop()  # Dừng bài hiện tại, hàm after sẽ tự động gọi bài tiếp theo
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


@bot.command(name='dung')
async def stop(ctx):
  guild_id = ctx.guild.id
  if guild_id in music_queues:
    music_queues[guild_id].clear()
  if ctx.voice_client:
    await ctx.voice_client.disconnect()
    await ctx.send('🛑 Đã dừng nhạc và ngắt kết nối khỏi phòng thoại!')


# Chạy bot bằng token của bạn (hoặc biến môi trường trên Render)
bot.run('DISCORD_TOKEN')
