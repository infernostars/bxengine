import re
from typing import Any

from bxengine.exceptions import BxeRuntimeSyntaxException
from bxengine.runtime.extensions.BxeExtension import BxeStatefulExtension, bpp_function


class DiscordStubExtension(BxeStatefulExtension):
    _bpp_function_category = "Discord"

    def __init__(self, runner: Any = None, channel: Any = None):
        self._runner = runner
        self._channel = channel
        self.buttons: list[list[str]] = []

    @bpp_function()
    def USERNAME(self):
        """Get the username of the user running the tag.
        @returns the runner's username"""
        return "TestUser"

    @bpp_function()
    def USERID(self):
        """Get the Discord ID of the user running the tag.
        @returns the runner's ID"""
        return 0

    @bpp_function()
    def CHANNEL(self):
        """Get the ID of the channel the tag was run in.
        @returns the channel ID"""
        return 0

    @bpp_function()
    def BUTTON(self, *args):
        """Create a button that can be pressed to rerun the tag with special arguments.
        @parameter args a string containing the arguments to run the tag with; if it's the string "null", disables the button
        @parameter label the label of the button
        @optional color the button color/style (`gray`, `blue`, `green`, or `red`)
        @optional locked whether the button is locked to only the current runner (`true`/`false`)
        @returns nothing"""
        self.buttons.append([str(a) for a in args])
        return ""


class BrainGlobalExtension(BxeStatefulExtension):
    _bpp_function_category = "Global Variables"

    def __init__(self, author: Any = None):
        self._author = str(author) if author is not None else ""
        self.global_variables: dict[str, Any] = {}

    @bpp_function("GLOBAL")
    def global_fn(self, func_type: str, variable: str, value: Any = None):
        """Works with global variables, variables that persist between tag runs.
        The creator of a global variable becomes its owner, and from then on only the owner and their tags may modify it. However, anybody may access the value of the variable.
        **GLOBAL DEFINE**: Defines or sets a global variable `v` to `s`.
        **GLOBAL VAR**: Gets the value of the global variable `s`.
        @parameter s the global variable to be accessed
        @parameter v (DEFINE) the value to set `s` to
        @returns (DEFINE) nothing
        @returns (VAR) the value of `s`"""
        if re.search(r"[^A-Za-z_0-9]", variable) or re.search(r"[0-9]", variable[0]):
            raise NameError(
                "Global variable name must be only letters, underscores and numbers, and cannot start with a number"
            )

        match str(func_type).lower():
            case "define":
                if len(str(value)) > 100_000:
                    raise ValueError("Global variables are capped at 100,000 characters or fewer")
                self.global_variables[variable] = value
                return ""
            case "var":
                if value:
                    raise BxeRuntimeSyntaxException("GLOBAL VAR expected 2 parameters, but got 3")
                if variable not in self.global_variables:
                    raise NameError(f"No global variable by the name {variable} defined")
                return self.global_variables[variable]
            case _:
                raise BxeRuntimeSyntaxException("GLOBAL needs a function type parameter")


class BrainUserExtension(BxeStatefulExtension):
    _bpp_function_category = "User Variables"

    def __init__(self, author: Any = None, runner: Any = None):
        self._author = str(author) if author is not None else ""
        if runner is not None and hasattr(runner, "id"):
            self._runner_id = str(runner.id)
        elif runner is not None:
            self._runner_id = str(runner)
        else:
            self._runner_id = "0"
        self.user_variables: dict[str, Any] = {}

    @bpp_function("USER")
    def user_fn(self, func_type: str, variable: str, value: Any = None, user: Any = None):
        """Works with user variables, variables that persist between tag runs and are unique to each user.
        The creator of a user variable becomes its owner, and from then on only the owner and their tags may modify it. However, anybody may access the value of the variable.
        **USER DEFINE**: Defines or sets a user variable `v` to `s`. Changes the runner's instance by default, but if another user has already created an instance, `id` can be used to change theirs.
        **USER VAR**: Gets the value of the user variable `s`. Gets the runner's instance by default, but `id` can be used to get a different user's instance.
        **USER LIST**: Gets a list of user IDs that have an instance of the user variable `s`.
        @parameter s the user variable to be accessed
        @parameter v (DEFINE) the value to set `s` to
        @optional id the user ID of a user that has defined an instance of the variable
        @returns (DEFINE) nothing
        @returns (VAR) the value of `s`
        @returns (LIST) a list of user IDs that have `s` defined"""
        if re.search(r"[^A-Za-z_0-9]", variable) or re.search(r"[0-9]", variable[0]):
            raise NameError(
                "User variable name must be only letters, underscores and numbers, and cannot start with a number"
            )

        target_user = self._runner_id if user is None else str(user)
        db_name = variable + ":" + target_user
        match str(func_type).lower():
            case "define":
                if len(str(value)) > 10_000:
                    raise ValueError("User variables are capped at 10,000 characters or fewer")
                self.user_variables[db_name] = value
                return ""
            case "var":
                if value:
                    db_name = variable + ":" + str(value)
                if db_name not in self.user_variables:
                    raise NameError(f"This user does not have {variable} defined")
                return self.user_variables[db_name]
            case "list":
                if value is not None or user is not None:
                    raise BxeRuntimeSyntaxException("USER LIST expected 2 parameters, but got more")

                users: set[str] = set()
                for local_name in self.user_variables.keys():
                    parts = str(local_name).split(":", 1)
                    if len(parts) == 2 and parts[0] == variable:
                        users.add(parts[1])
                return sorted(users)
            case _:
                raise BxeRuntimeSyntaxException("USER needs a function type parameter")
