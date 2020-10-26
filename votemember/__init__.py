from .votemember import VoteMember


def setup(bot):
    bot.add_cog(VoteMember(bot))