package com.postal.autoclip;

import com.google.inject.Provides;
import java.awt.Polygon;
import java.awt.Rectangle;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.inject.Inject;
import net.runelite.api.Actor;
import net.runelite.api.Client;
import net.runelite.api.Hitsplat;
import net.runelite.api.Player;
import net.runelite.api.events.ActorDeath;
import net.runelite.api.events.ChatMessage;
import net.runelite.api.events.GameTick;
import net.runelite.api.events.HitsplatApplied;
import net.runelite.api.events.InteractingChanged;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.events.NpcLootReceived;
import net.runelite.client.events.PlayerLootReceived;
import net.runelite.client.events.ServerNpcLoot;
import net.runelite.client.game.ItemManager;
import net.runelite.client.game.ItemStack;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;
import net.runelite.client.plugins.loottracker.LootReceived;

@PluginDescriptor(
    name = "Postal AutoClip Companion",
    description = "Sends local OSRS events and framing data to Postal AutoClip",
    tags = {"clips", "streaming", "loot", "pvp"}
)
public class PostalAutoClipPlugin extends Plugin
{
    @Inject private Client client;
    @Inject private PostalAutoClipConfig config;
    @Inject private ItemManager itemManager;

    private Actor recentInteractionTarget;
    private int recentInteractionTick = Integer.MIN_VALUE;
    private Actor recentDamageTarget;
    private int recentDamageTick = Integer.MIN_VALUE;
    private int recentDamageAmount = 0;
    private int lastHeartbeatTick = Integer.MIN_VALUE;
    private int lastFocusTick = Integer.MIN_VALUE;

    private final ExecutorService sender = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "postal-autoclip-event");
        t.setDaemon(true);
        return t;
    });

    @Override
    protected void startUp()
    {
        recentInteractionTarget = null;
        recentInteractionTick = Integer.MIN_VALUE;
        recentDamageTarget = null;
        recentDamageTick = Integer.MIN_VALUE;
        recentDamageAmount = 0;
        lastHeartbeatTick = Integer.MIN_VALUE;
        lastFocusTick = Integer.MIN_VALUE;
        send("bridge_online", 1.0, "{\"message\":\"Postal AutoClip RuneLite companion online\"}");
    }

    @Provides
    PostalAutoClipConfig provideConfig(ConfigManager configManager)
    {
        return configManager.getConfig(PostalAutoClipConfig.class);
    }

    @Subscribe
    public void onGameTick(GameTick event)
    {
        int tick = client.getTickCount();
        if (lastHeartbeatTick == Integer.MIN_VALUE || tick - lastHeartbeatTick >= 50)
        {
            lastHeartbeatTick = tick;
            send("bridge_heartbeat", 1.0, "{\"message\":\"RuneLite companion active\"}");
        }

        if (!config.smartFraming())
        {
            return;
        }

        Player local = client.getLocalPlayer();
        Actor target = local == null ? null : local.getInteracting();
        if (local != null && target != null
            && (lastFocusTick == Integer.MIN_VALUE || tick - lastFocusTick >= Math.max(1, config.focusSampleTicks())))
        {
            lastFocusTick = tick;
            String targetName = target.getName() == null ? "target" : target.getName();
            String targetType = target instanceof Player ? "player" : "npc";
            send("bridge_focus", 1.0, withFocus(
                "\"target_name\":\"" + esc(targetName) + "\",\"target_type\":\"" + targetType + "\"",
                target));
        }
    }

    @Subscribe
    public void onInteractingChanged(InteractingChanged event)
    {
        if (event.getSource() != client.getLocalPlayer() || event.getTarget() == null)
        {
            return;
        }

        recentInteractionTarget = event.getTarget();
        recentInteractionTick = client.getTickCount();
    }

    @Subscribe
    public void onNpcLootReceived(NpcLootReceived event)
    {
        String source = event.getNpc() != null && event.getNpc().getName() != null ? event.getNpc().getName() : "NPC";
        sendLoot("npc_loot", source, event.getItems(), true, event.getNpc());
    }

    @Subscribe
    public void onServerNpcLoot(ServerNpcLoot event)
    {
        String source = event.getComposition() != null && event.getComposition().getName() != null ? event.getComposition().getName() : "NPC";
        sendLoot("npc_loot", source, event.getItems(), true, null);
    }

    @Subscribe
    public void onPlayerLootReceived(PlayerLootReceived event)
    {
        String source = event.getPlayer() != null && event.getPlayer().getName() != null ? event.getPlayer().getName() : "player";
        sendLoot("player_loot", source, event.getItems(), false, event.getPlayer());
    }

    // Loot Tracker emits this for raids, chests and many non-NPC reward sources.
    @Subscribe
    public void onLootReceived(LootReceived event)
    {
        sendLoot("loot", event.getName() == null ? "loot" : event.getName(), event.getItems(), false, null);
    }

    @Subscribe
    public void onActorDeath(ActorDeath event)
    {
        Actor actor = event.getActor();
        if (!(actor instanceof Player))
        {
            return;
        }

        Player local = client.getLocalPlayer();
        String name = actor.getName() == null ? "unknown" : actor.getName();

        if (actor == local)
        {
            send("player_death", 1.0, withFocus(
                "\"actor_type\":\"player\",\"local_player\":true,\"name\":\"" + esc(name) + "\"",
                null));
            return;
        }

        int ticksSinceDamage = ticksSince(recentDamageTick);
        boolean confirmedDamage = actor == recentDamageTarget
            && ticksSinceDamage >= 0
            && ticksSinceDamage <= config.pvpKillWindowTicks();

        if (!confirmedDamage)
        {
            return;
        }

        boolean interactionMatch = actor == recentInteractionTarget || (local != null && local.getInteracting() == actor);
        int ticksSinceInteraction = actor == recentInteractionTarget ? ticksSince(recentInteractionTick) : -1;
        String fields = "\"actor_type\":\"player\",\"local_player\":false,"
            + "\"name\":\"" + esc(name) + "\","
            + "\"attributed_to_local\":true,"
            + "\"last_confirmed_damage\":" + recentDamageAmount + ","
            + "\"ticks_since_local_damage\":" + ticksSinceDamage + ","
            + "\"interaction_match\":" + interactionMatch + ","
            + "\"ticks_since_interaction\":" + ticksSinceInteraction;
        send("pvp_kill", 1.25, withFocus(fields, actor));
    }

    @Subscribe
    public void onHitsplatApplied(HitsplatApplied event)
    {
        Hitsplat hitsplat = event.getHitsplat();
        Actor actor = event.getActor();
        if (hitsplat == null || actor == null)
        {
            return;
        }

        int amount = hitsplat.getAmount();
        Player local = client.getLocalPlayer();

        // RuneLite's Hitsplat#isMine() is the same ownership signal used by the
        // built-in DPS counter for damage dealt by the local player.
        if (actor != local && hitsplat.isMine())
        {
            recentDamageTarget = actor;
            recentDamageTick = client.getTickCount();
            recentDamageAmount = amount;

            if (amount >= config.bigHit())
            {
                String name = actor.getName() == null ? "unknown" : actor.getName();
                String actorType = actor instanceof Player ? "player" : "npc";
                boolean interactionMatch = actor == recentInteractionTarget || (local != null && local.getInteracting() == actor);
                int ticksSinceInteraction = actor == recentInteractionTarget ? ticksSince(recentInteractionTick) : -1;
                String fields = "\"amount\":" + amount
                    + ",\"target_local\":false"
                    + ",\"attributed_to_local\":true"
                    + ",\"target_type\":\"" + actorType + "\""
                    + ",\"interaction_match\":" + interactionMatch
                    + ",\"ticks_since_interaction\":" + ticksSinceInteraction
                    + ",\"name\":\"" + esc(name) + "\"";
                send("big_hit", Math.min(1.5, 0.65 + amount / 100.0), withFocus(fields, actor));
            }
            return;
        }

        // Damage on the local player is useful clip context, but it is a
        // different event from damage dealt by the streamer.
        if (actor == local && amount >= config.bigHit())
        {
            String name = actor.getName() == null ? "local_player" : actor.getName();
            String fields = "\"amount\":" + amount
                + ",\"target_local\":true"
                + ",\"attributed_to_local\":false"
                + ",\"target_type\":\"player\""
                + ",\"name\":\"" + esc(name) + "\"";
            send("big_hit_taken", Math.min(1.35, 0.55 + amount / 110.0), withFocus(fields, null));
        }
    }

    @Subscribe
    public void onChatMessage(ChatMessage event)
    {
        if (!config.sendChat() || event.getMessage() == null)
        {
            return;
        }

        String clean = event.getMessage().replaceAll("<[^>]+>", "");
        String low = clean.toLowerCase(Locale.ROOT);
        String type = null;
        if (low.contains("new item added to your collection log"))
        {
            type = "collection_log";
        }
        else if (low.contains("oh dear, you are dead") || low.contains("you have died"))
        {
            type = "player_death";
        }
        else if (containsAny(low, "twisted bow", "tbow", "scythe", "tumeken", "shadow", "purple", "rare drop", "pet"))
        {
            type = "rare_drop";
        }
        else if (containsAny(low, "chambers of xeric", "theatre of blood", "tombs of amascut")
            && containsAny(low, "complete", "completed", "reward", "loot"))
        {
            type = "raid_complete";
        }

        if (type != null)
        {
            send(type, 1.0, withFocus("\"message\":\"" + esc(clean) + "\"", null));
        }
    }

    private int ticksSince(int tick)
    {
        if (tick == Integer.MIN_VALUE)
        {
            return Integer.MAX_VALUE;
        }
        return client.getTickCount() - tick;
    }

    private boolean containsAny(String text, String... words)
    {
        for (String w : words)
        {
            if (text.contains(w))
            {
                return true;
            }
        }
        return false;
    }

    private double[] actorCanvasRatio(Actor actor)
    {
        if (actor == null)
        {
            return null;
        }
        try
        {
            Polygon poly = actor.getCanvasTilePoly();
            if (poly == null)
            {
                return null;
            }
            Rectangle bounds = poly.getBounds();
            int canvasWidth = Math.max(1, client.getCanvasWidth());
            int canvasHeight = Math.max(1, client.getCanvasHeight());
            double x = Math.max(0.0, Math.min(1.0, bounds.getCenterX() / canvasWidth));
            double y = Math.max(0.0, Math.min(1.0, bounds.getCenterY() / canvasHeight));
            return new double[]{x, y};
        }
        catch (Exception ignored)
        {
            return null;
        }
    }

    private String focusFields(Actor target)
    {
        Player local = client.getLocalPlayer();
        double[] player = actorCanvasRatio(local);
        double[] targetPoint = actorCanvasRatio(target);
        double focusX = 0.5;
        double focusY = 0.5;
        if (player != null && targetPoint != null)
        {
            focusX = (player[0] + targetPoint[0]) / 2.0;
            focusY = (player[1] + targetPoint[1]) / 2.0;
        }
        else if (targetPoint != null)
        {
            focusX = targetPoint[0];
            focusY = targetPoint[1];
        }
        else if (player != null)
        {
            focusX = player[0];
            focusY = player[1];
        }

        StringBuilder sb = new StringBuilder();
        sb.append("\"canvas_width\":").append(Math.max(1, client.getCanvasWidth()));
        sb.append(",\"canvas_height\":").append(Math.max(1, client.getCanvasHeight()));
        sb.append(",\"focus_x_ratio\":").append(String.format(Locale.ROOT, "%.6f", focusX));
        sb.append(",\"focus_y_ratio\":").append(String.format(Locale.ROOT, "%.6f", focusY));
        if (player != null)
        {
            sb.append(",\"player_x_ratio\":").append(String.format(Locale.ROOT, "%.6f", player[0]));
            sb.append(",\"player_y_ratio\":").append(String.format(Locale.ROOT, "%.6f", player[1]));
        }
        if (targetPoint != null)
        {
            sb.append(",\"target_x_ratio\":").append(String.format(Locale.ROOT, "%.6f", targetPoint[0]));
            sb.append(",\"target_y_ratio\":").append(String.format(Locale.ROOT, "%.6f", targetPoint[1]));
        }
        return sb.toString();
    }

    private String withFocus(String fields, Actor target)
    {
        String base = fields == null ? "" : fields.trim();
        return "{" + base + (base.isEmpty() ? "" : ",") + focusFields(target) + "}";
    }

    private void sendLoot(String type, String source, Collection<ItemStack> items, boolean applyMinimum, Actor focusActor)
    {
        List<String> rows = new ArrayList<>();
        long totalValue = 0;
        if (items != null)
        {
            for (ItemStack item : items)
            {
                String name;
                try
                {
                    name = itemManager.getItemComposition(item.getId()).getName();
                }
                catch (Exception e)
                {
                    name = String.valueOf(item.getId());
                }

                long price = 0;
                try
                {
                    price = itemManager.getItemPrice(item.getId());
                }
                catch (Exception ignored)
                {
                }

                long value = Math.max(0L, price) * Math.max(0, item.getQuantity());
                totalValue += value;
                rows.add("{\"id\":" + item.getId()
                    + ",\"quantity\":" + item.getQuantity()
                    + ",\"name\":\"" + esc(name) + "\""
                    + ",\"price\":" + price
                    + ",\"value\":" + value + "}");
            }
        }

        if (applyMinimum && totalValue < config.minLootValue())
        {
            return;
        }

        String fields = "\"source\":\"" + esc(source)
            + "\",\"total_value\":" + totalValue
            + ",\"items\":[" + String.join(",", rows) + "]";
        send(type, 1.0, withFocus(fields, focusActor));
    }

    private void send(String eventType, double confidence, String payloadJson)
    {
        final String body = "{\"token\":\"" + esc(config.token())
            + "\",\"event_type\":\"" + esc(eventType)
            + "\",\"event_time\":" + (System.currentTimeMillis() / 1000.0)
            + ",\"confidence\":" + confidence
            + ",\"payload\":" + payloadJson + "}";

        // Network work never runs on the client thread. A single daemon worker
        // avoids spawning one thread for every hitsplat/loot event.
        sender.submit(() -> post(body));
    }

    private void post(String body)
    {
        HttpURLConnection con = null;
        try
        {
            con = (HttpURLConnection) new URL(config.endpoint()).openConnection();
            con.setConnectTimeout(600);
            con.setReadTimeout(600);
            con.setRequestMethod("POST");
            con.setRequestProperty("Content-Type", "application/json");
            con.setDoOutput(true);
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            try (OutputStream out = con.getOutputStream())
            {
                out.write(bytes);
            }
            con.getResponseCode();
        }
        catch (Exception ignored)
        {
            // AutoClip may be closed; gameplay must never be affected.
        }
        finally
        {
            if (con != null)
            {
                con.disconnect();
            }
        }
    }

    private static String esc(String s)
    {
        if (s == null)
        {
            return "";
        }
        return s.replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "");
    }
}
