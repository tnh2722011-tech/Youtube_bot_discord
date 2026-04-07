import discord
from discord.ext import commands, tasks
import yt_dlp
from datetime import datetime, timedelta
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.inactivity_starts = {}
bot.last_text_channels = {}
bot.current_owners = {}          # guild_id : member là chủ video đang phát

@bot.event
async def on_ready():
    print(f'✅ Bot đã online: {bot.user}')
    try:
        await bot.tree.sync()
        print("✅ Slash commands đã sync")
    except Exception as e:
        print(f"Lỗi sync: {e}")
    inactivity_check.start()

@tasks.loop(minutes=3)
async def inactivity_check():
    for guild_id in list(bot.inactivity_starts.keys()):
        start_time = bot.inactivity_starts[guild_id]
        guild = bot.get_guild(guild_id)
        if not guild:
            bot.inactivity_starts.pop(guild_id, None)
            continue
        vc = guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused():
            if datetime.now() - start_time > timedelta(minutes=15):
                await vc.disconnect()
                if guild_id in bot.last_text_channels:
                    try:
                        await bot.last_text_channels[guild_id].send("🚪 Bot đã rời kênh thoại do video đã phát xong và không có lệnh phát mới trong 15 phút.")
                    except:
                        pass
                bot.inactivity_starts.pop(guild_id, None)
                bot.last_text_channels.pop(guild_id, None)
                bot.current_owners.pop(guild_id, None)

@bot.tree.command(name="join", description="Bot join kênh thoại")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ Bạn phải ở trong kênh thoại!")
        return
    channel = interaction.user.voice.channel
    if interaction.guild.voice_client is not None:
        await interaction.response.send_message("✅ Bot đã ở trong kênh thoại rồi!")
        return
    try:
        vc = await channel.connect()
        await interaction.guild.me.edit(mute=True, deafen=True)
        await interaction.response.send_message(f"✅ Bot đã join **{channel.name}** (mic + loa đã tắt)")
    except Exception as e:
        await interaction.response.send_message(f"❌ Lỗi join: {str(e)}")

async def play_audio(vc, url, text_channel, owner):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info.get('title', 'Video YouTube')
    except Exception as e:
        await text_channel.send(f"❌ Không tải được video: {str(e)}")
        return

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -loglevel quiet',
    }
    source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options, executable='ffmpeg')

    def after_playing(error):
        if error:
            print(f"Player error: {error}")
        guild = vc.guild
        bot.inactivity_starts[guild.id] = datetime.now()
        bot.current_owners.pop(guild.id, None)   # Xóa owner khi video hết

    vc.play(source, after=after_playing)
    await text_channel.send(f"🎵 **Đang phát:** {title}\n👑 **Chủ video:** {owner.mention} (chỉ người này mới pause/resume được)")

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    content = message.content.strip()

    # Lệnh phat!
    if content.lower().startswith("phat! "):
        link = content[6:].strip()
        if not link:
            await message.channel.send("❌ Vui lòng gửi link YouTube sau lệnh `phat!`")
            return
        vc = message.guild.voice_client
        if not vc or not vc.is_connected():
            await message.channel.send("❌ Bot chưa join kênh thoại! Dùng lệnh `/join` trước.")
            return

        # Reset timer + set owner mới
        bot.inactivity_starts.pop(message.guild.id, None)
        bot.last_text_channels[message.guild.id] = message.channel
        bot.current_owners[message.guild.id] = message.author   # Người gõ phat! là owner

        if vc.is_playing() or vc.is_paused():
            vc.stop()

        await play_audio(vc, link, message.channel, message.author)

    # Lệnh dung! - Chỉ owner mới được dùng
    elif content.lower() == "dung!":
        vc = message.guild.voice_client
        if not vc or not vc.is_connected():
            await message.channel.send("❌ Bot chưa join kênh thoại!")
            return

        owner = bot.current_owners.get(message.guild.id)
        if owner and owner.id != message.author.id:
            await message.channel.send(f"❌ Chỉ **{owner.mention}** (người phát video) mới được dùng lệnh `dung!`")
            return

        if vc.is_playing():
            vc.pause()
            await message.channel.send("⏸️ Video đã tạm dừng!")
        elif vc.is_paused():
            vc.resume()
            await message.channel.send("▶️ Video đã tiếp tục phát!")
        else:
            await message.channel.send("Không có video nào đang phát.")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and after.channel is None:
        guild_id = before.channel.guild.id if before.channel else None
        if guild_id:
            bot.inactivity_starts.pop(guild_id, None)
            bot.last_text_channels.pop(guild_id, None)
            bot.current_owners.pop(guild_id, None)

def load_token():
    if not os.path.exists("Token.txt"):
        print("❌ Không tìm thấy file Token.txt!")
        exit(1)
    with open("Token.txt", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("token="):
                return line[6:].strip()
    print("❌ Không tìm thấy dòng token= trong Token.txt")
    exit(1)

if __name__ == "__main__":
    token = load_token()
    bot.run(token)