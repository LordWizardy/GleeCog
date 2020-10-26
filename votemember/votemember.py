import logging
import random
import string
from typing import Optional, cast

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

default_settings = {
    "ENABLED": False,
    "ROLE": [],
    "AGREE_CHANNEL": None,
    "AGREE_MSG": "{mention} wants to join the {roles} party",
    "POSITIVE_REACT": "✅",
    "POSITIVE_NEEDED": 1,
    "NEGATIVE_REACT": "❌",
    "NEGATIVE_NEEDED": 0,
    "VOTE_SUCCEEDED": "Voting successful, user {mention} was awarded role {roles} by users {people}",
    "VOTE_CANCELLED": "Voting of {mention} cancelled by users {people}"
}


log = logging.getLogger("red.GleeCog.votemember")

listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x

class VoteMember(commands.Cog):
    """
    commands on voting members
    """

    __author__ = ["tombuben"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1234123412)
        self.config.register_guild(**default_settings)
        self.users = {}
        self.messages = {}

    async def _no_perms(self, channel: Optional[discord.TextChannel] = None) -> None:
        m = (
            "It appears that you haven't given this "
            "bot enough permissions to use votemember. "
            'The bot requires the "Manage Roles" and '
            'the "Manage Messages" permissions in'
            "order to use votemember. You can change the "
            'permissions in the "Roles" tab of the '
            "guild settings."
        )
        if channel is None:
            log.info(m)
            return
        if channel.permissions_for(channel.guild.me).send_messages:
            await channel.send(m)
        else:
            log.info(m + "\n I also don't have permission to speak in #" + channel.name)

    async def get_colour(self, channel: discord.TextChannel) -> discord.Colour:
        try:
            return await self.bot.get_embed_colour(channel)
        except AttributeError:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()

    async def _agree_maker(self, member: discord.Member) -> None:
        guild = member.guild
        self.last_guild = guild
        # await self._verify_json(None)
        positive_react = await self.config.guild(guild).POSITIVE_REACT()
        negative_react = await self.config.guild(guild).NEGATIVE_REACT()
        roles = await self.config.guild(guild).ROLE()

        ch = cast(
            discord.TextChannel, guild.get_channel(await self.config.guild(guild).AGREE_CHANNEL())
        )
        msg = await self.config.guild(guild).AGREE_MSG()
        if msg is None:
            msg = "{mention} wants to join the {roles} party"
        try:
            msg = msg.format(
                mention=member.mention,
                roles=", ".join(role.mention for role in guild.roles if role.id in roles),
            )
        except Exception:
            log.error("Error formatting agreement message", exc_info=True)

        try:
            msg = await ch.send(msg)
            await msg.add_reaction(positive_react)
            if await self.config.guild(guild).NEGATIVE_NEEDED() > 0:
                await msg.add_reaction(negative_react)
        except discord.HTTPException:
            return
        self.messages[msg.id] = {"msg": msg, "member": member.id, "positive": set(), "negative": set()}

    async def _auto_give(self, member: discord.Member) -> None:
        guild = member.guild
        roles_id = await self.config.guild(guild).ROLE()
        roles = [role for role in guild.roles if role.id in roles_id]
        if not guild.me.guild_permissions.manage_roles:
            await self._no_perms()
            return
        for role in roles:
            await member.add_roles(member.guild.get_role(role), reason="Joined the server")

    async def _add_member_from_message(self, reaction_msg, add: bool) -> None:
        message = self.messages[reaction_msg]["msg"]
        guild = message.guild
        member = guild.get_member(self.messages[reaction_msg]["member"])
        roles = await self.config.guild(guild).ROLE()

        positive_react = await self.config.guild(guild).POSITIVE_REACT()
        negative_react = await self.config.guild(guild).NEGATIVE_REACT()

        roles_str = ", ".join(role.mention for role in guild.roles if role.id in roles)

        people = self.messages[reaction_msg]["positive" if add else "negative"]
        people = [guild.get_member(person) for person in people]
        people = list(filter(None, people))
        people_str = "Unknown"
        if people:
            people_str = ", ".join(
            [person.mention if hasattr(person, "mention") else person.name for person in people])


        await message.clear_reaction(positive_react)
        await message.clear_reaction(negative_react)

        if add:
            if not guild.me.guild_permissions.manage_roles:
                await self._no_perms()
                return
            for role in roles:
                await member.add_roles(member.guild.get_role(role), reason="Voted in by {people}".format(people=people_str))

        channel = message.channel
        msg = ""
        if add:
            msg = await self.config.guild(guild).VOTE_SUCCEEDED()
        else:
            msg = await self.config.guild(guild).VOTE_CANCELLED()
        msg = msg.format(
            mention=member.mention,
            roles=roles_str,
            people=people_str
        )
        await channel.send(msg)

        self.messages.pop(reaction_msg, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if await self.config.guild(guild).ENABLED():
            if await self.config.guild(guild).AGREE_CHANNEL() is not None:
                await self._agree_maker(member)
            else:  # Immediately give the new user the role
                await self._auto_give(member)

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.raw_models.RawReactionActionEvent
    ):
        if payload.user_id == self.bot.user.id:
            return

        reaction_msg = payload.message_id
        if reaction_msg not in self.messages:
            return

        guild = self.bot.get_guild(payload.guild_id)
        positive_react = await self.config.guild(guild).POSITIVE_REACT()
        positive_needed = await self.config.guild(guild).POSITIVE_NEEDED()
        negative_react = await self.config.guild(guild).NEGATIVE_REACT()
        negative_needed = await self.config.guild(guild).NEGATIVE_NEEDED()

        try:

            if str(payload.emoji) == positive_react:
                self.messages[reaction_msg]["positive"].add(payload.user_id)
            elif 0 < negative_needed and str(payload.emoji) == negative_react:
                self.messages[reaction_msg]["negative"].add(payload.user_id)

            if len(self.messages[reaction_msg]["positive"]) >= positive_needed:
                await self._add_member_from_message(reaction_msg, True)
            elif 0 < negative_needed <= len(self.messages[reaction_msg]["negative"]):
                await self._add_member_from_message(reaction_msg, False)
        except discord.HTTPException:
            return



    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.raw_models.RawReactionActionEvent
    ):
        reaction_msg = payload.message_id
        if reaction_msg not in self.messages:
            return

        guild = self.bot.get_guild(payload.guild_id)
        positive_react = await self.config.guild(guild).POSITIVE_REACT()
        negative_react = await self.config.guild(guild).NEGATIVE_REACT()

        if str(payload.emoji) == positive_react:
            self.messages[reaction_msg]["positive"].discard(payload.user_id)

        if str(payload.emoji) == negative_react:
            self.messages[reaction_msg]["negative"].discard(payload.user_id)

    @commands.guild_only()
    @commands.group(name="votemember")
    @commands.bot_has_permissions(manage_roles=True)
    async def votemember(self, ctx: commands.Context) -> None:
        """
        Change settings for votemember
        Requires the manage roles permission
        """
        pass

    @votemember.command(name="info")
    async def votemember_info(self, ctx: commands.Context) -> None:
        """
        Display current votemember info
        """
        guild = ctx.message.guild
        enabled = await self.config.guild(guild).ENABLED()
        roles = await self.config.guild(guild).ROLE()
        msg = await self.config.guild(guild).AGREE_MSG()
        if not msg:
            msg = "{mention} wants to join the {roles} party"
        positive_react = await self.config.guild(guild).POSITIVE_REACT()
        positive_needed = await self.config.guild(guild).POSITIVE_NEEDED()
        negative_react = await self.config.guild(guild).NEGATIVE_REACT()
        negative_needed = await self.config.guild(guild).NEGATIVE_NEEDED()
        succeeded_msg = await self.config.guild(guild).VOTE_SUCCEEDED()
        cancelled_msg = await self.config.guild(guild).VOTE_CANCELLED()

        ch_id = await self.config.guild(guild).AGREE_CHANNEL()
        channel = guild.get_channel(ch_id)
        chn_name = channel.name if channel is not None else "None"
        chn_mention = channel.mention if channel is not None else "None"
        role_name_str = ", ".join(role.mention for role in guild.roles if role.id in roles)
        if not role_name_str:
            role_name_str = "None"
        if ctx.channel.permissions_for(ctx.me).embed_links:
            embed = discord.Embed(colour=await self.get_colour(ctx.channel))
            embed.set_author(name="votemember settings for " + guild.name)
            embed.add_field(name="Current votemember state: ", value=str(enabled))
            embed.add_field(name="Current Roles: ", value=str(role_name_str))
            embed.add_field(name="Agreement message: ", value=str(msg))
            embed.add_field(name="Positive react:", value=str(positive_react))
            embed.add_field(name="Positive needed:", value=str(positive_needed))
            embed.add_field(name="Negative react:", value=str(negative_react))
            embed.add_field(name="Negative needed:", value=str(negative_needed))
            embed.add_field(name="Agreement channel: ", value=str(chn_mention))
            embed.add_field(name="Succeeded msg: ", value=str(succeeded_msg))
            embed.add_field(name="cancelled msg: ", value=str(cancelled_msg))
            await ctx.send(embed=embed)
        else:
            send_msg = (
                "```"
                + "Current votemember state: "
                + f"{enabled}\n"
                + "Current Roles: "
                + f"{role_name_str}\n"
                + "Agreement message: "
                + f"{msg}\n"
                + "Positive react: "
                + f"{positive_react}\n"
                + "Positive needed: "
                + f"{positive_needed}\n"
                + "Negative react: "
                + f"{negative_react}\n"
                + "Negative needed: "
                + f"{negative_needed}\n"
                + "Agreement channel: "
                + f"{chn_name}"
                + "Succeeded msg: "
                + f"{succeeded_msg}"
                + "Cancelled msg: "
                + f"{cancelled_msg}"
                + "```"
            )
            await ctx.send(send_msg)


    @votemember.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def toggle(self, ctx: commands.Context) -> None:
        """
        Enables/Disables votemember
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() is None:
            msg = "You haven't set a role to give to new users!"
            await ctx.send(msg)
        elif await self.config.guild(guild).AGREE_CHANNEL() is None:
            msg = "You haven't set a channel which will be used!"
            await ctx.send(msg)
        else:
            if await self.config.guild(guild).ENABLED():
                await self.config.guild(guild).ENABLED.set(False)
                await ctx.send("Votemember is now disabled.")
            else:
                await self.config.guild(guild).ENABLED.set(True)
                await ctx.send("Votemember is now enabled.")


    @votemember.command(name="add", aliases=["role"])
    @checks.admin_or_permissions(manage_roles=True)
    async def role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """
        Add a role for votemember to assign.
        You can use this command multiple times to add multiple roles.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if ctx.author.top_role < role:
            msg = (
                " is higher than your highest role. "
                "You can't assign votemember higher than your own"
            )
            await ctx.send(role.name + msg)
        if role.id in roles:
            await ctx.send(role.name + " is already in the votemember list.")
            return
        if guild.me.top_role < role:
            msg = " is higher than my highest role in the Discord hierarchy."
            await ctx.send(role.name + msg)
            return
        roles.append(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(role.name + " role added to the votemember.")

    @votemember.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """
        Remove a role from the votemember.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if role.id not in roles:
            await ctx.send(role.name + " is not in the votemember list.")
            return
        roles.remove(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(role.name + " role removed from the votemember.")

    @votemember.group()
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement(self, ctx: commands.Context) -> None:
        """
        Set the channel and message that will be used for accepting the rules.
        use the `votemember agreements setup` command to set it up
        """
        pass

    @agreement.command(name="channel")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the agreement channel
        Entering nothing will clear this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for votemember.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Votemember has been disabled, enable it first.")
            return
        if channel is None:
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await ctx.send("Agreement channel cleared")
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await ctx.send("Agreement channel set to " + channel.mention)

    @agreement.command(name="message", aliases=["msg"])
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_msg(self, ctx: commands.Context, *, message: str = None) -> None:
        """
        Set the agreement message
        `{mention}` Who should have the roles added.
        `{roles}` Which roles will be added
        Entering nothing will clear this to default.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for votemember.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Votemember has been disabled, enable it first.")
            return
        if message is None:
            await self.config.guild(guild).AGREE_MSG.set(None)
            await ctx.send("Agreement message cleared")
        else:
            await self.config.guild(guild).AGREE_MSG.set(message)
            await ctx.send("Agreement message set to " + message)

    @agreement.command(name="setup")
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement_setup(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = None,
        positive: str = ":white_check_mark:",
        pcount: int = 3,
        negative: str = ":x:",
        ncount: int = 1,
        msg: str = "{mention} wants to join the {roles} party",
    ) -> None:
        """
        Set the channel and message that will be used for accepting the rules.
        `channel` is the channel used.
        `msg` is the message sent to the channel.
        `positive` is the positive reaction channel members can cast
        `pcount` is the number of positive reactions required to get the roles
        `negative` is the negative reaction channel members can cast
        `ncount` is the number of negative reacts needed to disable voting
        Entering nothing will clear settings and disable votemember.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for votemember.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Votemember has been disabled, enable it first.")
            return
        if channel is None:
            await self.config.guild(guild).ENABLED.set(False)
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await self.config.guild(guild).AGREE_MSG.set(None)
            await self.config.guild(guild).POSITIVE_REACT.set(None)
            await self.config.guild(guild).POSITIVE_NEEDED.set(3)
            await self.config.guild(guild).NEGATIVE_REACT.set(None)
            await self.config.guild(guild).NEGATIVE_NEEDED.set(1)
            await ctx.send("Settings cleared and votemember disabled")
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await self.config.guild(guild).AGREE_MSG.set(msg)
            await self.config.guild(guild).POSITIVE_REACT.set(positive)
            await self.config.guild(guild).POSITIVE_NEEDED.set(pcount)
            await self.config.guild(guild).NEGATIVE_REACT.set(negative)
            await self.config.guild(guild).NEGATIVE_NEEDED.set(ncount)
            await ctx.send("Agreement channel set to " + channel.mention)


    @votemember.group()
    @checks.admin_or_permissions(manage_roles=True)
    async def response(self, ctx: commands.Context) -> None:
        """
        Set the responses after voting was finished
        """
        pass

    @response.command(name="succeeded")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_response_succeeded(self, ctx: commands.Context, *, message: str = None) -> None:
        """
        Set the successful voting message
        `{mention}` Who won the vote.
        `{roles}` Which roles will be added
        `{people}` Who voted positively
        Entering nothing will clear this to default.
        """
        guild = ctx.message.guild
        if message == None:
            message = "Voting successful, user {mention} was awarded role {roles} by users {people}"
        await self.config.guild(guild).VOTE_SUCCEEDED.set(message)


    @response.command(name="cancelled")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_response_cancelled(self, ctx: commands.Context, message: str = None) -> None:
        """
        Set the successful voting message
        `{mention}` Who won the vote.
        `{roles}` Which roles will be added
        `{people}` Who voted positively
        Entering nothing will clear this to default.
        """
        guild = ctx.message.guild
        if message == None:
            message = "Voting of {mention} cancelled by users {people}"
        await self.config.guild(guild).VOTE_CANCELLED.set(message)