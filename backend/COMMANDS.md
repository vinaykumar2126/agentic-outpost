# Check if it's running
launchctl list | grep eventsfinder

# Stop it
launchctl unload ~/Library/LaunchAgents/com.vinaykumar.eventsfinder.plist

# Start it again
launchctl load ~/Library/LaunchAgents/com.vinaykumar.eventsfinder.plist

# Watch live logs
tail -f ~/events_finder/backend/logs/server.log
