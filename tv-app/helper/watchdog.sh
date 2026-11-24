#!/system/bin/sh
while true; do
  if [ "$(settings get global low_power_standby_enabled)" = 1 ]; then
    date >> /data/local/tmp/watchdog.log
  fi
  settings put global low_power_standby_enabled 0
  sleep 30
done
