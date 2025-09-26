import discord
from discord import app_commands
from discord.ext import commands
import redis
import json
import os
import random

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Redis connection
r = redis.Redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# Restrict slash commands to your server
GUILD_ID = discord.Object(id=1196690004852883507)

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=GUILD_ID)
        print(f"🔧 {len(synced)} commands synced with the server.")
    except Exception as e:
        print(f"Sync error: {e}")

# --- Slash Commands ---

# 🎰 Gacha
@bot.tree.command(name="gacha", description="Try your luck at the gacha!", guild=GUILD_ID)
async def gacha(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tickets = int(r.get(f"tickets:{user_id}") or 0)

    if tickets <= 0:
        return await interaction.response.send_message(
            "❌ You don't own a Gacha Ticket. Contact <@912376040142307419> or <@801879772421423115>",
            ephemeral=True
        )

    r.decr(f"tickets:{user_id}")
    rewards = r.lrange("rewards:remaining", 0, -1)
    if not rewards:
        return await interaction.response.send_message("🎉 No rewards left!")

    reward = random.choice(rewards)
    r.lrem("rewards:remaining", 1, reward)
    r.rpush("rewards:history", json.dumps({"user": user_id, "reward": reward}))

    await interaction.response.send_message(f"🎊 Congrats <@{user_id}>! You won **Reward {reward}**!")

    channel = bot.get_channel(int(os.getenv("REWARD_CHANNEL")))
    if channel:
        await channel.send(f"🎁 <@{user_id}> just won **Reward {reward}**!")

# 🎟️ Add a gacha ticket
@bot.tree.command(name="add-gachaticket", description="Add a gacha ticket to a player", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def add_ticket(interaction: discord.Interaction, member: discord.Member):
    r.incr(f"tickets:{member.id}")
    await interaction.response.send_message(f"🎟️ Ticket added to {member.mention}")

# 📦 Remaining rewards
@bot.tree.command(name="remaining-rewards", description="See remaining rewards", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def remaining(interaction: discord.Interaction):
    rewards = r.lrange("rewards:remaining", 0, -1)
    if not rewards:
        return await interaction.response.send_message("📦 No rewards left.")

    rewards_int = list(map(int, rewards))
    summary = {
        "1-5": sum(1 for x in rewards_int if 1 <= x <= 5),
        "6-10": sum(1 for x in rewards_int if 6 <= x <= 10),
        "11-20": sum(1 for x in rewards_int if 11 <= x <= 20),
        "21-50": sum(1 for x in rewards_int if 21 <= x <= 50),
        "51-200": sum(1 for x in rewards_int if 51 <= x <= 200),
    }

    msg = "📦 **Remaining rewards:**\n"
    for group, count in summary.items():
        msg += f"- {group} → {count}\n"

    if len(rewards_int) <= 10:
        msg += "\n🔍 Detail: " + ", ".join(map(str, sorted(rewards_int)))

    await interaction.response.send_message(msg)

# 🔄 Reset gacha
@bot.tree.command(name="reset-gacha", description="Reset all rewards", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    r.delete("rewards:remaining")
    initial_rewards = ["1","2","3","4","5"]
    initial_rewards += [str(i) for i in range(6, 11)]
    initial_rewards += [str(i) for i in range(11, 21)]
    initial_rewards += [str(i) for i in range(21, 51)]
    initial_rewards += [str(i) for i in range(51, 201)]
    r.rpush("rewards:remaining", *initial_rewards)
    await interaction.response.send_message("🔄 Gacha reset with all rewards!")

# 📜 Rewards history
@bot.tree.command(name="rewards", description="See your reward history", guild=GUILD_ID)
async def rewards(interaction: discord.Interaction):
    history = r.lrange("rewards:history", -10, -1)
    if not history:
        return await interaction.response.send_message("📜 No history yet.")
    parsed = [json.loads(h) for h in history]
    msg = "\n".join([f"<@{h['user']}> → Reward {h['reward']}" for h in parsed])
    await interaction.response.send_message(f"📜 History:\n{msg}")

# 🏆 Last winners
@bot.tree.command(name="last-winners", description="See the last winners", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def last_winners(interaction: discord.Interaction, count: int = 5):
    history = r.lrange("rewards:history", -count, -1)
    if not history:
        return await interaction.response.send_message("📜 No winners yet.")
    parsed = [json.loads(h) for h in history]
    msg = "🏆 **Last winners:**\n"
    for h in parsed:
        msg += f"- <@{h['user']}> → Reward {h['reward']}\n"
    await interaction.response.send_message(msg)

# 💎 Give shards
@bot.tree.command(name="give-shards", description="Give Shards of Awesomeness to a player", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def give_shards(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

    r.incrby(f"shards:{member.id}", amount)
    total = int(r.get(f"shards:{member.id}") or 0)
    await interaction.response.send_message(f"💎 {amount} Shards given to {member.mention}. Current total: {total}")

# 💎 Remove shards
@bot.tree.command(name="remove-shards", description="Remove Shards of Awesomeness from a player", guild=GUILD_ID)
@app_commands.checks.has_permissions(administrator=True)
async def remove_shards(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

    current = int(r.get(f"shards:{member.id}") or 0)
    if current < amount:
        return await interaction.response.send_message(
            f"⚠️ {member.mention} only has {current} Shards, cannot remove {amount}.",
            ephemeral=True
        )

    r.decrby(f"shards:{member.id}", amount)
    total = int(r.get(f"shards:{member.id}") or 0)
    await interaction.response.send_message(f"💎 {amount} Shards removed from {member.mention}. Current total: {total}")

# 💎 Check shards
@bot.tree.command(name="shards", description="Check your Shards of Awesomeness", guild=GUILD_ID)
async def shards(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    total = int(r.get(f"shards:{user_id}") or 0)
    await interaction.response.send_message(f"💎 You currently have **{total} Shards of Awesomeness**.")

# --- Run the bot ---
bot.run(os.getenv("BOT_TOKEN"))
