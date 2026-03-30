"""
Focus Engine Pro — DNS Blocker & Incognito Registry Toggle
Sets Cloudflare Family DNS (1.1.1.3) to block adult content system-wide.
Toggles Chrome/Edge incognito mode via Windows Registry when focus mode changes.
Requires Administrator privileges.
"""

import subprocess
import winreg
import ctypes
import os


class DNSBlocker:
    """Manages DNS settings and browser incognito registry keys."""

    SAFE_DNS_PRIMARY = "1.1.1.3"
    SAFE_DNS_SECONDARY = "1.0.0.3"

    def __init__(self):
        self._original_dns = {}  # adapter_name -> original DNS
        self._is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    # ── DNS Management ────────────────────────────────────────────────────

    def enable_safe_mode(self):
        """Set DNS to Cloudflare Family on all active network adapters."""
        if not self._is_admin:
            print("[!] DNS Blocker requires admin privileges. Skipping.")
            return False

        adapters = self._get_active_adapters()
        for adapter in adapters:
            try:
                # Set primary DNS
                subprocess.run(
                    ["netsh", "interface", "ip", "set", "dns",
                     f"name={adapter}", "static", self.SAFE_DNS_PRIMARY],
                    capture_output=True, check=True
                )
                # Set secondary DNS
                subprocess.run(
                    ["netsh", "interface", "ip", "add", "dns",
                     f"name={adapter}", self.SAFE_DNS_SECONDARY, "index=2"],
                    capture_output=True, check=True
                )
                print(f"  [+] DNS set to Cloudflare Family on: {adapter}")
            except subprocess.CalledProcessError as e:
                print(f"  [!] Failed to set DNS on {adapter}: {e}")

        # Flush DNS cache
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        return True

    def disable_safe_mode(self):
        """Restore DNS to automatic (DHCP) on all adapters."""
        if not self._is_admin:
            return False

        adapters = self._get_active_adapters()
        for adapter in adapters:
            try:
                subprocess.run(
                    ["netsh", "interface", "ip", "set", "dns",
                     f"name={adapter}", "dhcp"],
                    capture_output=True, check=True
                )
                print(f"  [+] DNS restored to DHCP on: {adapter}")
            except subprocess.CalledProcessError:
                pass

        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        return True

    def is_enabled(self) -> bool:
        """Check if any adapter has our safe DNS."""
        try:
            result = subprocess.run(
                ["netsh", "interface", "ip", "show", "dns"],
                capture_output=True, text=True
            )
            return self.SAFE_DNS_PRIMARY in result.stdout
        except Exception:
            return False

    def _get_active_adapters(self) -> list:
        """Get names of active network adapters."""
        try:
            result = subprocess.run(
                ["netsh", "interface", "show", "interface"],
                capture_output=True, text=True
            )
            adapters = []
            for line in result.stdout.strip().split("\n")[3:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0].lower() in ("enabled",):
                    # "Enabled" adapters — name is everything after the 3rd column
                    if parts[1].lower() == "connected":
                        name = " ".join(parts[3:])
                        adapters.append(name)
            return adapters if adapters else ["Wi-Fi", "Ethernet"]
        except Exception:
            return ["Wi-Fi", "Ethernet"]

    # ── Incognito Mode Registry Toggle ────────────────────────────────────

    def block_incognito(self):
        """Disable incognito/private mode in Chrome and Edge via registry."""
        if not self._is_admin:
            print("[!] Need admin to modify registry. Skipping incognito block.")
            return False

        # Chrome
        self._set_registry_value(
            r"SOFTWARE\Policies\Google\Chrome",
            "IncognitoModeAvailability", 1
        )
        # Edge
        self._set_registry_value(
            r"SOFTWARE\Policies\Microsoft\Edge",
            "InPrivateModeAvailability", 1
        )
        print("  [+] Incognito / InPrivate mode BLOCKED via registry")
        return True

    def unblock_incognito(self):
        """Re-enable incognito/private mode."""
        if not self._is_admin:
            return False

        # Chrome
        self._delete_registry_value(
            r"SOFTWARE\Policies\Google\Chrome",
            "IncognitoModeAvailability"
        )
        # Edge
        self._delete_registry_value(
            r"SOFTWARE\Policies\Microsoft\Edge",
            "InPrivateModeAvailability"
        )
        print("  [+] Incognito / InPrivate mode RESTORED")
        return True

    def _set_registry_value(self, key_path: str, value_name: str, value: int):
        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE, key_path,
                0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
            )
            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value)
            winreg.CloseKey(key)
        except PermissionError:
            print(f"  [!] Cannot write registry: {key_path}\\{value_name}")
        except Exception as e:
            print(f"  [!] Registry error: {e}")

    def _delete_registry_value(self, key_path: str, value_name: str):
        try:
            key = winreg.OpenKeyEx(
                winreg.HKEY_LOCAL_MACHINE, key_path,
                0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
            )
            winreg.DeleteValue(key, value_name)
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass  # Key doesn't exist, that's fine
        except Exception:
            pass
