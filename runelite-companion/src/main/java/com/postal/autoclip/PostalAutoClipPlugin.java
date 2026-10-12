package com.postal.autoclip;

import com.google.inject.Provides;
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
import net.runelite.api.Player;
import net.runelite.api.events.ActorDeath;
import net.runelite.api.events.ChatMessage;
import net.runelite.api.events.HitsplatApplied;
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
    description = "Sends local OSRS events to Postal AutoClip for accurate clip timing",
    tags = {"clips", "streaming", "loot", "pvp"}
)
public class PostalAutoClipPlugin extends Plugin
{
    @Inject private Client client;
    @Inject private PostalAutoClipConfig config;
    @Inject private ItemManager itemManager;
    private final ExecutorService sender = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "postal-autoclip-event");
        t.setDaemon(true);
        return t;
    });

    @Override
    protected void startUp()
    {
        send("bridge_online", 1.0, "{\"message\":\"Postal AutoClip RuneLite companion online\"}");
    }

    @Provides
    PostalAutoClipConfig provideConfig(ConfigManager configManager)
    {
        return configManager.getConfig(PostalAutoClipConfig.class);
    }

    @Subscribe
    public void onNpcLootReceived(NpcLootReceived event)
    {
        String source = event.getNpc() != null && event.getNpc().getName() != null ? event.getNpc().getName() : "NPC";
        sendLoot("npc_loot", source, event.getItems(), true);
    }

    @Subscribe
    public void onServerNpcLoot(ServerNpcLoot event)
    {
        String source = event.getComposition() != null && event.getComposition().getName() != null ? event.getComposition().getName() : "NPC";
        sendLoot("npc_loot", source, event.getItems(), true);
    }

    @Subscribe
    public void onPlayerLootReceived(PlayerLootReceived event)
    {
        String source = event.getPlayer() != null && event.getPlayer().getName() != null ? event.getPlayer().getName() : "player";
        sendLoot("player_loot", source, event.getItems(), false);
    }

    // Loot Tracker emits this for raids, chests and many non-NPC reward sources.
    @Subscribe
    public void onLootReceived(LootReceived event)
    {
        sendLoot("loot", event.getName() == null ? "loot" : event.getName(), event.getItems(), false);
    }

    @Subscribe
    public void onActorDeath(ActorDeath event)
    {
        Actor actor = event.getActor();
        if (actor == null) return;
        boolean isPlayer = actor instanceof Player;
        if (!isPlayer) return;
        boolean isLocal = actor == client.getLocalPlayer();
        String name = actor.getName() == null ? "unknown" : actor.getName();
        String payload = "{\"actor_type\":\"" + (isPlayer ? "player" : "npc") + "\",\"local_player\":" + isLocal + ",\"name\":\"" + esc(name) + "\"}";
        send("actor_death", 1.0, payload);
    }

    @Subscribe
    public void onHitsplatApplied(HitsplatApplied event)
    {
        if (event.getHitsplat() == null || event.getActor() == null) return;
        int amount = event.getHitsplat().getAmount();
        if (amount < config.bigHit()) return;
        Actor actor = event.getActor();
        boolean targetLocal = actor == client.getLocalPlayer();
        String name = actor.getName() == null ? "unknown" : actor.getName();
        String payload = "{\"amount\":" + amount + ",\"target_local\":" + targetLocal + ",\"name\":\"" + esc(name) + "\"}";
        send("big_hit", Math.min(1.5, 0.65 + amount / 100.0), payload);
    }

    @Subscribe
    public void onChatMessage(ChatMessage event)
    {
        if (!config.sendChat() || event.getMessage() == null) return;
        String clean = event.getMessage().replaceAll("<[^>]+>", "");
        String low = clean.toLowerCase(Locale.ROOT);
        String type = null;
        if (low.contains("new item added to your collection log")) type = "collection_log";
        else if (low.contains("oh dear, you are dead") || low.contains("you have died")) type = "player_death";
        else if (containsAny(low, "twisted bow", "tbow", "scythe", "tumeken", "shadow", "purple", "rare drop", "pet")) type = "rare_drop";
        else if (containsAny(low, "chambers of xeric", "theatre of blood", "tombs of amascut") && containsAny(low, "complete", "completed", "reward", "loot")) type = "raid_complete";
        if (type != null)
        {
            send(type, 1.0, "{\"message\":\"" + esc(clean) + "\"}");
        }
    }

    private boolean containsAny(String text, String... words)
    {
        for (String w : words) if (text.contains(w)) return true;
        return false;
    }

    private void sendLoot(String type, String source, Collection<ItemStack> items, boolean applyMinimum)
    {
        List<String> rows = new ArrayList<>();
        long totalValue = 0;
        if (items != null)
        {
            for (ItemStack item : items)
            {
                String name;
                try { name = itemManager.getItemComposition(item.getId()).getName(); }
                catch (Exception e) { name = String.valueOf(item.getId()); }
                int price = 0;
                try { price = itemManager.getItemPrice(item.getId()); } catch (Exception ignored) { }
                long value = (long) Math.max(0, price) * Math.max(0, item.getQuantity());
                totalValue += value;
                rows.add("{\"id\":" + item.getId() + ",\"quantity\":" + item.getQuantity() + ",\"name\":\"" + esc(name) + "\",\"price\":" + price + ",\"value\":" + value + "}");
            }
        }
        if (applyMinimum && totalValue < config.minLootValue()) return;
        String payload = "{\"source\":\"" + esc(source) + "\",\"total_value\":" + totalValue + ",\"items\":[" + String.join(",", rows) + "]}";
        send(type, 1.0, payload);
    }

    private void send(String eventType, double confidence, String payloadJson)
    {
        final String body = "{\"token\":\"" + esc(config.token()) + "\",\"event_type\":\"" + esc(eventType) + "\",\"event_time\":" + (System.currentTimeMillis() / 1000.0) + ",\"confidence\":" + confidence + ",\"payload\":" + payloadJson + "}";
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
            try (OutputStream out = con.getOutputStream()) { out.write(bytes); }
            con.getResponseCode();
        }
        catch (Exception ignored)
        {
            // AutoClip may be closed; gameplay must never be affected.
        }
        finally
        {
            if (con != null) con.disconnect();
        }
    }

    private static String esc(String s)
    {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "");
    }
}
