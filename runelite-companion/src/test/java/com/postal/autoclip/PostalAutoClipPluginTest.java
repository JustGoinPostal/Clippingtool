package com.postal.autoclip;

import net.runelite.client.RuneLite;
import net.runelite.client.externalplugins.ExternalPluginManager;

public class PostalAutoClipPluginTest
{
    public static void main(String[] args) throws Exception
    {
        ExternalPluginManager.loadBuiltin(PostalAutoClipPlugin.class);
        RuneLite.main(args);
    }
}
