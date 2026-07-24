"""
╔══════════════════════════════════════════════════════════════╗
║              ATTRIBUTE AUTHORITY  (attribute_authority.py)   ║
║  Manages policy catalog and provides attribute lists to       ║
║  the MA-ABE setup used by Fog, Cloud, and Data User.          ║
╚══════════════════════════════════════════════════════════════╝
"""

import re

DIVIDER = "─" * 55

class AttributeAuthority:

    def __init__(self):
        print(DIVIDER)
        print("🏛️  [AA] Attribute Authority initializing…")

        # ── Policy catalog ─────────────────────────────────────
        # Keys   : human-readable policy names (sent to IoT devices)
        # Values : boolean access-tree string understood by MA-ABE yj14
        #          Use plain UPPERCASE attribute names — no @AUTHID suffix.
        self.master_catalog = {
            "policy1"    : "((STUDENT or STAFF))",
            "policy2"    : "((MANAGER and RESEARCHER))",
            "Admin_Only" : "(ADMIN)",
        }

        print(f"   ✅ Policy catalog loaded — {len(self.master_catalog)} policies:")
        for name, expr in self.master_catalog.items():
            print(f"      📋 {name:15s} → {expr}")
        print(DIVIDER)

    # ── Public API ──────────────────────────────────────────────

    def get_fog_payload(self) -> dict:
        """
        Returns the full policy catalog.
        The fog node sends the policy *names* to the IoT device,
        then uses the corresponding *expression* to encrypt KI.
        """
        return self.master_catalog

    def get_all_attributes(self) -> list:
        """
        Extracts and returns every unique plain attribute name across
        all policies.  Passed directly to maabe.setupAuthority().
        Excludes boolean operators (AND / OR / NOT).
        """
        all_attrs = set()
        for policy_text in self.master_catalog.values():
            tokens = re.findall(r'\b[A-Z_]+\b', policy_text.upper())
            for token in tokens:
                if token not in ('OR', 'AND', 'NOT'):
                    all_attrs.add(token)

        attr_list = list(all_attrs)
        print(f"🏛️  [AA] All attributes for authority setup: {attr_list}")
        return attr_list

    def get_policy_expression(self, policy_name: str) -> str | None:
        """
        Return the boolean expression for a given policy name.
        Returns None if the name is not recognised.
        """
        expr = self.master_catalog.get(policy_name)
        if expr is None:
            print(f"⚠️  [AA] WARNING — unknown policy name: '{policy_name}'")
        return expr

    def list_policies(self) -> list:
        """Return just the policy names (sent to IoT devices)."""
        return list(self.master_catalog.keys())


# ── Module-level singletons used by every other module ─────────
aa          = AttributeAuthority()
fog_payload = aa.get_fog_payload()