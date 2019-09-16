from redbot.core import commands
import discord
import sys
from random import choice
import random
import json

folderPath = "/home/bastion/red_data/cogs/CogManager/cogs/gleecog/"

class Gleecog(commands.Cog):

    @commands.command(name="quote", aliases=["q"])
    async def quote(self, ctx):
        """Picks a random quote"""

        with open("quotes.json") as f:
            data = json.load(f)


        #with open(folderPath + 'quotes.json', 'r', encoding='utf-8') as qList:
        #    quoteList = qList.readlines()
        #    pick = random.randint(0,len(quoteList)-1)
        await ctx.send(data[0]['test'])