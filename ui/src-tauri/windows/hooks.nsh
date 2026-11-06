; Kill running OnTheSpot processes before installation
!macro NSIS_HOOK_PREINSTALL
  ; Kill the main app process
  nsExec::Exec 'taskkill /F /IM "OnTheSpot.exe"'
  ; Kill the backend sidecar process
  nsExec::Exec 'taskkill /F /IM "ots-backend.exe"'
  ; Small delay to ensure processes are fully terminated and file handles released
  Sleep 1500
!macroend
