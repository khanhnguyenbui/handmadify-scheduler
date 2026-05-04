import discord
from discord.ext import commands
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from db import Database

load_dotenv()

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
db = Database()

# ── Dashboard View (Permanent UI) ──────────────────────────────────────────

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Add Market", style=discord.ButtonStyle.primary, custom_id="db_add", emoji="➕")
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select Market Type:", view=CreateFlowView(), ephemeral=True)

    @discord.ui.button(label="Edit Market", style=discord.ButtonStyle.secondary, custom_id="db_edit", emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        markets = db.get_all_markets()
        if not markets: return await interaction.response.send_message("No markets to edit.", ephemeral=True)
        await interaction.response.send_message("Choose a market:", view=EditFlowView(markets), ephemeral=True)

    @discord.ui.button(label="Sync", style=discord.ButtonStyle.success, custom_id="db_sync", emoji="🔄")
    async def sync_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.load()
        await sync_all_displays(interaction.guild)
        await interaction.response.send_message("✅ Dashboard synchronized.", ephemeral=True)

# ── Sync Logic ───────────────────────────────────────────────────────────────

async def sync_all_displays(guild: discord.Guild):
    all_markets = sorted(db.get_all_markets(), key=lambda x: x["date"])
    
    dashboard_embed = discord.Embed(title="📅 Market Command Center", color=0x57F287)
    dashboard_embed.description = (
        "🥬 **Soulard Farmers Market:** Sat 8:30-3:30 (Summer) | All year.\n"
        "🌳 **Tower Grove Farmers Market:** Sat 7:00-1:30 | April-Nov."
    )
    for m in all_markets:
        staff_list = m.get("assigned_staff", [])
        staff_mentions = ", ".join(f"<@{uid}>" for uid in staff_list) if staff_list else "None"
        dashboard_embed.add_field(
            name=f"{m['date']} | {m['market_type']}",
            value=f"Staff: {staff_mentions}\nNotes: {m.get('notes', 'None')}",
            inline=False
        )

    # Sync Dashboard(s)
    for dash in db.get_dashboards():
        try:
            channel = guild.get_channel(dash["channel_id"]) or await guild.fetch_channel(dash["channel_id"])
            msg = await channel.fetch_message(dash["message_id"])
            await msg.edit(embed=dashboard_embed, view=DashboardView())
        except Exception as e: 
            print(f"Error updating dashboard: {e}")

    # Sync Market Cards
    for m in all_markets:
        if m.get("message_id"):
            try:
                staff_list = m.get("assigned_staff", [])
                embed = discord.Embed(title=f"🛒 {m['market_type']} - {m['date']}", color=0x5865F2)
                embed.add_field(name="Staff", value=", ".join(f"<@{uid}>" for uid in staff_list) or "None", inline=False)
                embed.add_field(name="Notes", value=m.get("notes", "None"), inline=False)
                
                channel = guild.get_channel(m["channel_id"]) or await guild.fetch_channel(m["channel_id"])
                msg = await channel.fetch_message(m["message_id"])
                await msg.edit(embed=embed)
            except Exception as e:
                print(f"Error updating market card {m['id']}: {e}")

# ── Views & Modals ──────────────────────────────────────────────────────────

class MarketBaseModal(discord.ui.Modal):
    def __init__(self, title, initial_date="", initial_notes=""):
        super().__init__(title=title)
        self.date_input = discord.ui.TextInput(label="Date (YYYY-MM-DD)", default=initial_date, placeholder="2025-06-07")
        self.notes_input = discord.ui.TextInput(label="Special Notes", style=discord.TextStyle.paragraph, default=initial_notes, required=False)
        self.add_item(self.date_input)
        self.add_item(self.notes_input)

class StaffSelectView(discord.ui.View):
    def __init__(self, market_id: int):
        super().__init__(timeout=None)
        self.market_id = market_id
        self.select = discord.ui.UserSelect(placeholder="Select Staff", min_values=0, max_values=25)
        self.add_item(self.select)

    @discord.ui.button(label="Save Staff", style=discord.ButtonStyle.green)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        staff_ids = [str(u.id) for u in self.select.values]
        market = db.get_market(self.market_id)
        db.update_market(self.market_id, market["date"], market["notes"], staff_ids)
        await sync_all_displays(interaction.guild)
        await interaction.followup.send("✅ Market Saved & Synced!", ephemeral=True)

class CreateFlowView(discord.ui.View):
    @discord.ui.select(placeholder="Choose Market Type...", options=[
        discord.SelectOption(label="Soulard"), 
        discord.SelectOption(label="Tower Grove"),
        discord.SelectOption(label="Other Event")
    ])
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        market_type = select.values[0]
        modal = MarketBaseModal(title=f"New {market_type} Market")
        async def on_submit(i: discord.Interaction):
            mid = db.create_market(market_type, modal.date_input.value, modal.notes_input.value, [], i.channel_id)
            await i.response.send_message(f"Now assigning staff for {market_type}:", view=StaffSelectView(mid), ephemeral=True)
            msg = await i.channel.send("Initializing market card...")
            db.set_message_id(mid, msg.id)
            await sync_all_displays(i.guild)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

class EditFlowView(discord.ui.View):
    def __init__(self, markets):
        super().__init__()
        options = [discord.SelectOption(label=f"{m['date']} | {m['market_type']}", value=str(m['id'])) for m in markets]
        self.select = discord.ui.Select(placeholder="Select Market to Edit", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        mid = int(self.select.values[0])
        m = db.get_market(mid)
        modal = MarketBaseModal(title="Edit Market", initial_date=m["date"], initial_notes=m["notes"])
        async def on_submit(i: discord.Interaction):
            db.update_market(mid, modal.date_input.value, modal.notes_input.value, m["assigned_staff"])
            await i.response.send_message(f"Now updating staff for {m['market_type']}:", view=StaffSelectView(mid), ephemeral=True)
            await sync_all_displays(i.guild)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

# ── Commands ────────────────────────────────────────────────────────────────

@bot.tree.command(name="dashboard")
async def dashboard(interaction: discord.Interaction):
    msg = await interaction.channel.send("Initializing Dashboard...")
    db.add_dashboard(interaction.channel_id, msg.id)
    await sync_all_displays(interaction.guild)
    await interaction.response.send_message("Dashboard created.", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(DashboardView())
    await bot.tree.sync()
    print("✅ Bot ready and DashboardView registered.")

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN not found in .env file!")
    bot.run(token)