package com.bobassistant.helper;

import android.content.AttributionSource;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.pm.ApplicationInfo;
import android.os.Looper;
import android.os.Process;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

final class Shell extends ContextWrapper {
    static final String PACKAGE = "com.android.shell";
    private static Shell instance;

    private Shell(Context base) {
        super(base);
    }

    static synchronized Shell get() throws Exception {
        if (instance == null) {
            Looper.prepareMainLooper();
            Class<?> threadClass = Class.forName("android.app.ActivityThread");
            Constructor<?> constructor = threadClass.getDeclaredConstructor();
            constructor.setAccessible(true);
            Object thread = constructor.newInstance();
            Field current = threadClass.getDeclaredField("sCurrentActivityThread");
            current.setAccessible(true);
            current.set(null, thread);
            Field system = threadClass.getDeclaredField("mSystemThread");
            system.setAccessible(true);
            system.setBoolean(thread, true);
            Class<?> bindClass = Class.forName("android.app.ActivityThread$AppBindData");
            Constructor<?> bindConstructor = bindClass.getDeclaredConstructor();
            bindConstructor.setAccessible(true);
            Object bind = bindConstructor.newInstance();
            ApplicationInfo info = new ApplicationInfo();
            info.packageName = PACKAGE;
            Field infoField = bindClass.getDeclaredField("appInfo");
            infoField.setAccessible(true);
            infoField.set(bind, info);
            Field bound = threadClass.getDeclaredField("mBoundApplication");
            bound.setAccessible(true);
            bound.set(thread, bind);
            Method systemContext = threadClass.getDeclaredMethod("getSystemContext");
            instance = new Shell((Context) systemContext.invoke(thread));
        }
        return instance;
    }

    @Override
    public String getPackageName() {
        return PACKAGE;
    }

    @Override
    public String getOpPackageName() {
        return PACKAGE;
    }

    @Override
    public AttributionSource getAttributionSource() {
        return new AttributionSource.Builder(Process.SHELL_UID).setPackageName(PACKAGE).build();
    }

    @Override
    public Context getApplicationContext() {
        return this;
    }

    public int getDeviceId() {
        return 0;
    }
}
