#!/bin/sh
# Помощник звука на ТВ: снимает микрофон и опорный канал (звук самого ТВ) из процесса shell
# и шлёт их Боба на Мак, где из микрофона вычитается звук ТВ.
# Нужна включённая «Отладка по Wi-Fi». После каждой перезагрузки ТВ запускать заново.
#   tv-helper.sh start [<ip Мака>]    собрать, поставить и запустить (сам перезапускается при сбоях)
#   tv-helper.sh stop
#   tv-helper.sh status
# Адрес ТВ берётся из ANDROID_SERIAL (adb connect уже сделан).
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
PORT=8766
case "$1" in
  start)
    HOST=${2:-$(ipconfig getifaddr en0)}
    TOKEN=$(cat "$ROOT/server/secrets/token")
    "$DIR/build.sh" >/dev/null
    adb push "$DIR/build/helper.jar" /data/local/tmp/bobhelper.jar >/dev/null
    adb shell "pkill -f com.bobassistant.helper.Stream" < /dev/null 2>/dev/null || true
    adb shell "cd /data/local/tmp && nohup setsid sh -c 'while true; do CLASSPATH=/data/local/tmp/bobhelper.jar app_process /system/bin com.bobassistant.helper.Stream $HOST $PORT $TOKEN; sleep 5; done' >/dev/null 2>&1 &" < /dev/null
    echo "помощник запущен"
    ;;
  stop)
    adb shell "pkill -f com.bobassistant.helper.Stream" || true
    echo "помощник остановлен"
    ;;
  status)
    adb shell "ps -A | grep -c 'com.bobassistant.helper.Stream' || true"
    ;;
  *)
    echo "usage: $0 start [mac-ip] | stop | status"
    exit 1
    ;;
esac
