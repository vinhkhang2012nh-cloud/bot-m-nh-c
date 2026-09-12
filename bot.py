import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

# Cấu hình cơ bản
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Cấu hình yt-dlp (Đã thêm cookiefile để chống lỗi anti-bot của YouTube)
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'cookiesfrombrowser': ('chrome',), # Tự động lấy cookie từ Chrome trên máy tính của bạn
}

# Cấu hình ffmpeg cho Linux/Docker trên Render (không trỏ đường dẫn ổ C nữa)
ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập thành công dưới tên: {bot.user}')

@bot.command(name='phat', help='Phát nhạc từ từ khóa hoặc link')
async def phat(ctx, *, query=None):
    if not query:
        await ctx.send("Vui lòng nhập tên bài hát hoặc link cần phát nhé!")
        return
    
    if not ctx.author.voice:
        await ctx.send("Bạn phải vào một phòng Voice trước đã!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect(timeout=60.0, reconnect=True)
    else:
        await ctx.voice_client.move_to(channel)

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f'Lỗi âm thanh: {e}') if e else None)
            await ctx.send(f'🎶 Đang phát: **{player.title}**')
        except Exception as e:
            await ctx.send(f"Đã xảy ra lỗi khi phát nhạc: {e}")

@bot.command(name='stop', help='Dừng nhạc và đuổi bot ra khỏi phòng')
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Đã dừng nhạc và ngắt kết nối!")

bot.run(os.getenv("DISCORD_TOKEN"))
