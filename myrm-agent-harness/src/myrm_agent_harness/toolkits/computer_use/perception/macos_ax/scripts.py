"""AppleScript sources of the macOS AX snapshot and invoke.

[INPUT]
- dref.types::INTERACTIVE_AX_ROLES (POS: role strings an AX element is interactive under)

[OUTPUT]
- _AX_SNAPSHOT_SCRIPT, _build_ax_snapshot_script: AX tree capture script (whole app, query, role filter)
- _AX_INVOKE_SCRIPT, _build_ax_invoke_script: AX element action script
- _MAX_ELEMENTS, _SNAPSHOT_ROLE_FILTER: capture cap and the roles a snapshot keeps
- _build_app_selector, _TARGET_APP_BUNDLE_IDS: how a script finds its target application process

[POS]
The osascript text the capture and invoke modules run; nothing here executes a process.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.computer_use.dref.types import INTERACTIVE_AX_ROLES

_MAX_ELEMENTS = 500

# System Events reports AX-prefixed and human-readable role strings depending on macOS version.
_SNAPSHOT_ROLE_FILTER: tuple[str, ...] = tuple(
    sorted(
        set(INTERACTIVE_AX_ROLES)
        | {
            "button",
            "checkbox",
            "combo box",
            "pop up button",
            "radio button",
            "slider",
            "tab group",
            "text field",
            "text area",
            "static text",
            "menu item",
            "link",
        },
        key=str.lower,
    )
)

_SNAPSHOT_ALWAYS_EMIT_ROLES: tuple[str, ...] = tuple(
    sorted(
        {
            "AXButton",
            "AXCheckBox",
            "AXTextField",
            "AXTextArea",
            "AXPopUpButton",
            "AXRadioButton",
            "Button",
            "CheckBox",
            "EditControl",
            "RadioButtonControl",
            "button",
            "checkbox",
            "text field",
            "text area",
            "pop up button",
            "radio button",
        },
        key=str.lower,
    )
)


def _applescript_string_list(values: tuple[str, ...]) -> str:
    return ", ".join(f'"{value}"' for value in values)


_TARGET_APP_BUNDLE_IDS: dict[str, str] = {
    "TextEdit": "com.apple.TextEdit",
}


def _build_app_selector(target_app: str | None) -> str:
    if not target_app:
        return "set targetApp to first application process whose frontmost is true"
    bundle_id = _TARGET_APP_BUNDLE_IDS.get(target_app)
    if bundle_id:
        return f'set targetApp to first application process whose bundle identifier is "{bundle_id}"'
    escaped = target_app.replace('"', '\\"')
    # Exact name first; contains fallback so short names like "Excel" match "Microsoft Excel".
    # AppleScript's `whose A or B` does not guarantee exact-priority, so use try/on error.
    return (
        "try\n"
        f'    set targetApp to first application process whose name is "{escaped}"\n'
        "on error\n"
        f'    set targetApp to first application process whose name contains "{escaped}"\n'
        "end try"
    )


def _build_ax_snapshot_script(
    *, target_app: str | None = None, query: str | None = None, role: str | None = None
) -> str:
    role_filter = _applescript_string_list(_SNAPSHOT_ROLE_FILTER)
    always_emit_roles = _applescript_string_list(_SNAPSHOT_ALWAYS_EMIT_ROLES)
    app_selector = _build_app_selector(target_app)
    query_str = (query or "").lower().strip().replace('"', '\\"')
    role_str = (role or "").lower().strip().replace('"', '\\"')
    return f"""
on escapeText(t)
    if t is missing value then return ""
    set s to t as string
    set soh to ASCII character 1
    set out to ""
    set n to count of s
    repeat with i from 1 to n
        set c to character i of s
        if c is ASCII character 10 then
            set c to soh
        else if c is ASCII character 13 then
            set c to soh
        else if c is ASCII character 92 then
            set out to out & c & c
        else if c is "|" then
            set out to out & "/"
        else
            set out to out & c
        end if
    end repeat
    return out
end escapeText

tell application "System Events"
    {app_selector}
    try
        if value of attribute "AXMinimized" of window 1 of targetApp is true then
            set value of attribute "AXMinimized" of window 1 of targetApp to false
            delay 0.05
        end if
    end try
    set appName to name of targetApp
    set bundleId to ""
    try
        set bundleId to bundle identifier of targetApp
    end try
    set appPid to unix id of targetApp
    set winTitle to ""
    try
        set winTitle to name of window 1 of targetApp
    end try

    set outputLines to {{}}
    set end of outputLines to appName & "|||META|||" & winTitle & "|||" & bundleId & "|||" & appPid

    set uiElements to {{}}
    try
        set uiElements to entire contents of window 1 of targetApp
    on error errMsg
        if errMsg contains "assistive access" or errMsg contains "辅助访问" then
            set end of outputLines to "AX_PERMISSION_ERROR|||" & errMsg
            set AppleScript's text item delimiters to linefeed
            return outputLines as string
        end if
    end try
    try
        set maxElements to count of uiElements
        set targetQuery to "{query_str}"
        set targetRole to "{role_str}"
        if targetQuery is "" and targetRole is "" then
            if maxElements > {_MAX_ELEMENTS} then set maxElements to {_MAX_ELEMENTS}
        end if
        set collectedCount to 0
        repeat with i from 1 to maxElements
            set elem to item i of uiElements
            try
                set elemRole to role of elem
                if elemRole is in {{{role_filter}}} then
                    -- macOS reports a password field with role AXTextField; only its subrole
                    -- identifies it. Resolve the secure role *before* reading anything, so the
                    -- secret is never read out of the accessibility tree at all.
                    set reportRole to elemRole
                    try
                        if (subrole of elem) is "AXSecureTextField" then set reportRole to "AXSecureTextField"
                    end try
                    set elemName to ""
                    set elemValue to ""
                    try
                        set elemName to name of elem
                    end try
                    if reportRole is not "AXSecureTextField" then
                        try
                            set elemValue to value of elem
                        end try
                    end if
                    if elemName is missing value then set elemName to ""
                    if elemValue is missing value then set elemValue to ""

                    set matchQuery to true
                    if targetQuery is not "" then
                        set lowerName to (elemName as text)
                        set lowerVal to (elemValue as text)
                        if (lowerName does not contain targetQuery) and (lowerVal does not contain targetQuery) then
                            set matchQuery to false
                        end if
                    end if

                    set matchRole to true
                    if targetRole is not "" then
                        set lowerRole to (elemRole as text)
                        if lowerRole does not contain targetRole then
                            set matchRole to false
                        end if
                    end if

                    if matchQuery and matchRole then
                        if elemName is not "" or elemValue is not "" or elemRole is in {{{always_emit_roles}}} then
                            set safeName to my escapeText(elemName)
                            set safeValue to my escapeText(elemValue)
                            set elemPos to position of elem
                            set elemSize to size of elem
                            set end of outputLines to ((i as text) & "|||" & reportRole & "|||" & safeName & "|||" & safeValue & "|||" & (item 1 of elemPos as text) & "|||" & (item 2 of elemPos as text) & "|||" & (item 1 of elemSize as text) & "|||" & (item 2 of elemSize as text))
                            set collectedCount to collectedCount + 1
                            if collectedCount >= {_MAX_ELEMENTS} then exit repeat
                        end if
                    end if
                end if
            end try
        end repeat
    end try

    set AppleScript's text item delimiters to linefeed
    return outputLines as string
end tell
"""


_AX_SNAPSHOT_SCRIPT = _build_ax_snapshot_script()


def _build_ax_invoke_script(target_app: str | None = None) -> str:
    app_selector = _build_app_selector(target_app)
    return f"""
on escapeText(t)
    if t is missing value then return ""
    set s to t as string
    set bs to ASCII character 92
    set dq to ASCII character 34
    set s to my replaceText(s, bs, bs & bs)
    set s to my replaceText(s, dq, bs & dq)
    return s
end escapeText

on replaceText(sourceText, oldText, newText)
    set AppleScript's text item delimiters to oldText
    set parts to text items of sourceText
    set AppleScript's text item delimiters to newText
    set resultText to parts as string
    set AppleScript's text item delimiters to ""
    return resultText
end replaceText

on run argv
    set actionName to item 1 of argv
    set elemIndex to item 2 of argv as integer
    set inputText to item 3 of argv

    tell application "System Events"
        {app_selector}
        try
            if value of attribute "AXMinimized" of window 1 of targetApp is true then
                set value of attribute "AXMinimized" of window 1 of targetApp to false
                delay 0.05
            end if
        end try
        set uiElements to entire contents of window 1 of targetApp
        set elem to item elemIndex of uiElements
        if actionName is "fill" then
            set value of elem to inputText
            return "OK"
        end if
        if actionName is "set_value" then
            set value of elem to inputText
            return "OK"
        end if
        if actionName is "click" then
            try
                perform action "AXPress" of elem
                return "OK"
            on error
                click elem
                return "OK"
            end try
        end if
        if actionName is "press" then
            perform action "AXPress" of elem
            return "OK"
        end if
        return "UNSUPPORTED"
    end tell
end run
"""


_AX_INVOKE_SCRIPT = _build_ax_invoke_script()
