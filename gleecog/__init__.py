from .gleecog import Gleecog


def setup(bot):
    bot.add_cog(Gleecog(bot))