import discord
from discord.ext import commands
import json
import os
import requests
import base64
from datetime import datetime

TOKEN = "MTQ3MTQ2NDA4MTU0MTAzODIyMg.G4hayn.IipgHe15W7IXmOphp9fBAxDIHJTwWyPfsbaC58"
GITHUB_TOKEN = "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"
REPO_NAME = "Comment-creator/rage-transcripts"
BASE_URL = "https://comment-creator.github.io/rage-transcripts/"
STAFF_ROLE_NAME = "Support"
LOG_CHANNEL_NAME = "ticket-logs"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= Ticket Counter =================

if not os.path.exists("ticket_count.json"):
    with open("ticket_count.json", "w") as f:
        json.dump({"count": 0}, f)

def get_ticket_number():
    with open("ticket_count.json", "r") as f:
        data = json.load(f)
    data["count"] += 1
    with open("ticket_count.json", "w") as f:
        json.dump(data, f)
    return f"{data['count']:02d}"

# ================= Upload To GitHub =================

def upload_to_github(file_name):
    with open(file_name, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_name}"

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    data = {
        "message": f"Upload {file_name}",
        "content": content
    }

    response = requests.put(url, json=data, headers=headers)
    return response.status_code in [200, 201]

# ================= HTML Transcript =================

async def create_transcript(channel):
    messages_html = ""

    async for msg in channel.history(limit=None, oldest_first=True):
        time = msg.created_at.strftime("%Y-%m-%d %H:%M")
        content = msg.content.replace("<", "&lt;").replace(">", "&gt;") if msg.content else ""

        messages_html += f"""
        <div class="message">
            <div class="author">{msg.author}</div>
            <div class="time">{time}</div>
            <div class="content">{content}</div>
        </div>
        """

    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{channel.name} Transcript</title>
        <style>
            body {{ background:#1e1f22; color:#dcddde; font-family:Arial; padding:20px; }}
            .message {{ margin-bottom:15px; padding:10px; background:#2b2d31; border-radius:8px; }}
            .author {{ font-weight:bold; color:#5865F2; }}
            .time {{ font-size:12px; color:#949ba4; }}
        </style>
    </head>
    <body>
        <h2>Transcript - {channel.name}</h2>
        {messages_html}
    </body>
    </html>
    """

    file_name = f"{channel.name}.html"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(html_content)

    return file_name

# ================= Ticket Control =================

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.claimed_by = None

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.close_ticket(interaction, "No reason specified")

    @discord.ui.button(label="🔒 Close With Reason", style=discord.ButtonStyle.danger, custom_id="ticket_close_reason")
    async def close_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseReasonModal(self))

    @discord.ui.button(label="🧑‍💼 Claim", style=discord.ButtonStyle.success, custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):

        support_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME)

        if not support_role or support_role not in interaction.user.roles:
            await interaction.response.send_message("❌ فقط السابورت يقدر يستلم التيكت.", ephemeral=True)
            return

        if self.claimed_by:
            await interaction.response.send_message("❌ التيكت متاخدة بالفعل.", ephemeral=True)
            return

        self.claimed_by = interaction.user
        button.label = "Claimed"
        button.style = discord.ButtonStyle.secondary
        button.disabled = True

        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            title="✅ Claimed Ticket",
            description=f"Your ticket will be handled by {interaction.user.mention}",
            color=0x2ecc71
        )

        await interaction.channel.send(embed=embed)

    async def close_ticket(self, interaction, reason):

        log_channel = discord.utils.get(interaction.guild.text_channels, name=LOG_CHANNEL_NAME)

        topic_data = interaction.channel.topic.split("|")
        user_id = int(topic_data[0])
        open_timestamp = float(topic_data[1])

        ticket_owner = interaction.guild.get_member(user_id)
        open_time = datetime.fromtimestamp(open_timestamp)
        close_time = datetime.utcnow()

        claimed_text = self.claimed_by.mention if self.claimed_by else "Not claimed"

        file_name = await create_transcript(interaction.channel)
        uploaded = upload_to_github(file_name)
        public_url = f"{BASE_URL}{file_name}"

        embed = discord.Embed(title="Ticket Closed", color=0x2b2d31)
        embed.add_field(name="🎫 Ticket ID", value=interaction.channel.name, inline=False)
        embed.add_field(name="🟢 Opened By", value=ticket_owner.mention if ticket_owner else "Unknown", inline=True)
        embed.add_field(name="🔴 Closed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="🟣 Claimed By", value=claimed_text, inline=True)
        embed.add_field(name="⏰ Open Time", value=open_time.strftime("%B %d, %Y %I:%M %p"), inline=False)
        embed.add_field(name="📄 Reason", value=reason, inline=False)
        embed.set_footer(text=close_time.strftime("%m/%d/%Y %I:%M %p"))

        view = discord.ui.View()
        if uploaded:
            view.add_item(discord.ui.Button(
                label="View Online Transcript",
                style=discord.ButtonStyle.link,
                url=public_url
            ))

        if log_channel:
            await log_channel.send(embed=embed, view=view)

        if ticket_owner:
            try:
                await ticket_owner.send(embed=embed, view=view)
            except:
                pass

        os.remove(file_name)
        await interaction.channel.delete()

# ================= Modal =================

class CloseReasonModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Close Ticket")
        self.view = view

    reason = discord.ui.TextInput(label="سبب القفل", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.close_ticket(interaction, self.reason.value)

# ================= Ticket Select =================

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Technical Support", emoji="🛠️"),
            discord.SelectOption(label="Game Issue", emoji="🎮"),
            discord.SelectOption(label="Ban / Anti-Cheat / Chat Block", emoji="🚫"),
        ]
        super().__init__(placeholder="Choose ticket category...", options=options, custom_id="ticket_select")

    async def callback(self, interaction: discord.Interaction):

        for channel in interaction.guild.text_channels:
            if channel.name.startswith("ticket-") and channel.topic and channel.topic.startswith(str(interaction.user.id)):
                await interaction.response.send_message("❌ عندك تيكت مفتوحة بالفعل.", ephemeral=True)
                return

        await interaction.response.defer()

        ticket_number = get_ticket_number()
        category_name = self.values[0]

        category = discord.utils.get(interaction.guild.categories, name=category_name)
        if not category:
            category = await interaction.guild.create_category(category_name)

        support_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        open_time = datetime.utcnow().timestamp()

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_number}",
            category=category,
            overwrites=overwrites,
            topic=f"{interaction.user.id}|{open_time}"
        )

        mention_text = ""
        if support_role:
            mention_text += support_role.mention + " "
        mention_text += interaction.user.mention

        msg = await channel.send(mention_text)
        await msg.delete(delay=2)

        embed = discord.Embed(
            description=(
                "Thank you for contacting support.\n"
                "شكراً لتواصلك مع فريق الدعم.\n\n"
                "Please describe your issue and wait for a response.\n"
                "من فضلك اكتب مشكلتك بالتفصيل وانتظر رد فريق الدعم."
            ),
            color=0x2ecc71
        )

        embed.set_footer(text="Powered by Rage Ticket")

        await channel.send(embed=embed, view=TicketControlView())
        await interaction.message.edit(view=TicketView())

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.add_view(TicketView())
    bot.add_view(TicketControlView())

@bot.command()
async def setup(ctx):

    embed = discord.Embed(
        title="📩 OPEN A TICKET",
        description="Click the button below to open a support ticket.",
        color=0x00b0f4
    )

    # 👇 حط هنا لينك الصورة
    embed.set_image(url="https://media.discordapp.net/attachments/1465677664349061152/1467463652302127279/SUPPORT_with_logo.png?ex=698efa06&is=698da886&hm=e00aa4547e8bc846eb4e22402774fbb0be7635d47d7d9cd049f1f90eb76ab78a&=&format=webp&quality=lossless&width=1005&height=628")

    embed.set_footer(text="Powered by Rage Ticket")

    await ctx.send(embed=embed, view=TicketView())

bot.run(TOKEN)
