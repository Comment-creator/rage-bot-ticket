import discord
from discord.ext import commands
import os
import asyncio
from datetime import datetime

TOKEN = os.getenv("TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_USERNAME = "Comment-creator"
REPO_NAME = "rage-transcripts"
SUPPORT_ROLE_NAME = "Support"
TICKET_CATEGORY_NAME = "Tickets"
LOG_CHANNEL_NAME = "ticket-logs"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

ticket_counter = 1


# ================= TRANSCRIPT HTML =================

def generate_html(messages, ticket_name):
    html_content = f"""
    <html>
    <head>
        <title>{ticket_name}</title>
        <style>
            body {{ background:#0f0f0f; color:white; font-family:Arial; }}
            .msg {{ margin-bottom:15px; padding:10px; background:#1c1c1c; border-radius:8px; }}
            .author {{ font-weight:bold; }}
            .time {{ font-size:12px; color:gray; }}
        </style>
    </head>
    <body>
    <h2>{ticket_name}</h2>
    """

    for msg in messages:
        html_content += f"""
        <div class="msg">
            <div class="author">{msg.author}</div>
            <div>{msg.content}</div>
            <div class="time">{msg.created_at}</div>
        </div>
        """

    html_content += "</body></html>"

    os.makedirs("transcripts", exist_ok=True)
    with open(f"transcripts/{ticket_name}.html", "w", encoding="utf-8") as f:
        f.write(html_content)


# ================= VIEW BUTTON =================

class TranscriptButton(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="📄 View Online Transcript",
                style=discord.ButtonStyle.primary,
                url=url
            )
        )


# ================= CLOSE MODAL =================

class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await close_ticket(interaction, self.reason.value)


# ================= TICKET ACTION VIEW =================

class TicketActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="close_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction, "No reason specified")

    @discord.ui.button(label="📄 Close With Reason", style=discord.ButtonStyle.danger, custom_id="close_reason_btn")
    async def close_reason_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseReasonModal())

    @discord.ui.button(label="🧑‍💻 Claim", style=discord.ButtonStyle.success, custom_id="claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):

        support_role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLE_NAME)

        if support_role not in interaction.user.roles:
            return await interaction.response.send_message(
                "❌ Only support can claim.",
                ephemeral=True
            )

        button.label = "Claimed"
        button.disabled = True

        await interaction.message.edit(view=self)

        await interaction.channel.send(
            embed=discord.Embed(
                description=f"✅ **Claimed Ticket**\nYour ticket will be handled by {interaction.user.mention}",
                color=discord.Color.green()
            )
        )

        await interaction.response.defer()


# ================= CLOSE FUNCTION =================

async def close_ticket(interaction, reason):

    support_role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLE_NAME)

    if support_role not in interaction.user.roles:
        return await interaction.response.send_message(
            "❌ Only support can close tickets.",
            ephemeral=True
        )

    channel = interaction.channel
    ticket_name = channel.name
    guild = interaction.guild

    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    generate_html(messages, ticket_name)

    transcript_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/{ticket_name}.html"

    owner_id = int(channel.topic)
    owner = guild.get_member(owner_id)

    embed = discord.Embed(title="Ticket Closed", color=discord.Color.red())
    embed.add_field(name="🎟️ Ticket ID", value=ticket_name, inline=False)
    embed.add_field(name="🟢 Opened By", value=owner.mention if owner else "Unknown")
    embed.add_field(name="🔴 Closed By", value=interaction.user.mention)
    embed.add_field(name="📄 Reason", value=reason, inline=False)
    embed.add_field(name="⏰ Time", value=datetime.now().strftime("%B %d, %Y %I:%M %p"))

    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    if log_channel:
        await log_channel.send(embed=embed, view=TranscriptButton(transcript_url))

    if owner:
        try:
            await owner.send(embed=embed, view=TranscriptButton(transcript_url))
        except:
            pass

    await channel.delete()


# ================= TICKET SELECT =================

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Technical Support", emoji="🛠️"),
            discord.SelectOption(label="Game Issue", emoji="🎮"),
            discord.SelectOption(label="Ban / Anti-Cheat / Chat Block", emoji="🚫"),
        ]

        super().__init__(
            placeholder="Choose ticket category...",
            options=options,
            custom_id="ticket_select"
        )

    async def callback(self, interaction: discord.Interaction):
        global ticket_counter

        for channel in interaction.guild.text_channels:
            if channel.topic == str(interaction.user.id):
                return await interaction.response.send_message(
                    "❌ You already have an open ticket.",
                    ephemeral=True
                )

        category = discord.utils.get(interaction.guild.categories, name=TICKET_CATEGORY_NAME)

        if not category:
            category = await interaction.guild.create_category(TICKET_CATEGORY_NAME)

        support_role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLE_NAME)

        ticket_name = f"ticket-{ticket_counter:02d}"
        ticket_counter += 1

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            support_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            ticket_name,
            category=category,
            overwrites=overwrites,
            topic=str(interaction.user.id)
        )

        await channel.send(
            f"{interaction.user.mention} {support_role.mention}",
            embed=discord.Embed(
                description="Thank you for contacting support.\nPlease describe your issue and wait for response.",
                color=discord.Color.green()
            ),
            view=TicketActions()
        )

        await interaction.response.send_message("✅ Ticket created!", ephemeral=True)


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ================= READY =================
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


@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(TicketActions())
    print(f"Logged in as {bot.user}")


bot.run(TOKEN)
