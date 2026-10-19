package com.postal.autoclip;

import net.runelite.client.config.Config;
import net.runelite.client.config.ConfigGroup;
import net.runelite.client.config.ConfigItem;
import net.runelite.client.config.Range;

@ConfigGroup("postalautoclip")
public interface PostalAutoClipConfig extends Config
{
    @ConfigItem(keyName = "endpoint", name = "Postal AutoClip URL", description = "Local Postal AutoClip endpoint")
    default String endpoint()
    {
        return "http://127.0.0.1:8787/api/game-events";
    }

    @ConfigItem(keyName = "token", name = "Bridge token", description = "Must match runelite_bridge_token in Postal AutoClip config.json")
    default String token()
    {
        return "postal-local";
    }

    @Range(min = 1, max = 120)
    @ConfigItem(keyName = "bigHit", name = "Big hit threshold", description = "Send locally-attributed outgoing or incoming hits at or above this damage amount")
    default int bigHit()
    {
        return 35;
    }

    @Range(min = 1, max = 30)
    @ConfigItem(keyName = "pvpKillWindowTicks", name = "PvP kill attribution window", description = "How many game ticks after your last confirmed damage on a player their death can count as your PvP kill")
    default int pvpKillWindowTicks()
    {
        return 12;
    }

    @Range(min = 0, max = 100000000)
    @ConfigItem(keyName = "minLootValue", name = "NPC loot minimum value", description = "Ignore ordinary NPC loot below this estimated GE value. PvP and raid/reward events are still sent.")
    default int minLootValue()
    {
        return 100000;
    }

    @ConfigItem(keyName = "sendChat", name = "Important chat messages", description = "Send likely collection-log/drop/raid/death chat messages")
    default boolean sendChat()
    {
        return true;
    }

    @ConfigItem(keyName = "smartFraming", name = "Smart framing data", description = "Send normalized player/target screen positions to AutoClip for accurate vertical reframing")
    default boolean smartFraming()
    {
        return true;
    }

    @Range(min = 1, max = 10)
    @ConfigItem(keyName = "focusSampleTicks", name = "Framing sample ticks", description = "While interacting with a target, send one framing sample every N game ticks")
    default int focusSampleTicks()
    {
        return 2;
    }
}
