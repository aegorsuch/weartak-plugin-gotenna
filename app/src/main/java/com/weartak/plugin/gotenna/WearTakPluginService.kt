package com.weartak.plugin.gotenna

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.IBinder
import android.os.RemoteException
import android.util.Log
import com.weartak.plugin.sdk.MainUiActionContract
import com.weartak.plugin.sdk.WearTakPluginContract
import com.weartak.plugin.sdk.aidl.IWearTakHostCallback
import com.weartak.plugin.sdk.aidl.IWearTakPlugin
import com.weartak.plugin.sdk.aidl.IWearTakPluginControl
import com.weartak.plugin.sdk.lifecycle.PluginLifecycleEvent
import com.weartak.plugin.sdk.lifecycle.PluginLifecycleMachine
import com.weartak.plugin.sdk.model.HostSettingsParcel
import com.weartak.plugin.sdk.model.MainUiCardParcel
import com.weartak.plugin.sdk.model.MainUiCardTypes
import com.weartak.plugin.sdk.model.PluginCapabilitiesParcel
import com.weartak.plugin.sdk.model.PluginErrorCodes
import com.weartak.plugin.sdk.model.PluginErrorParcel
import com.weartak.plugin.sdk.model.PluginInfoParcel
import com.weartak.plugin.sdk.model.PluginInitParcel
import com.weartak.plugin.sdk.model.PluginMainUiSchemaParcel
import com.weartak.plugin.sdk.model.PluginStatusParcel
import com.weartak.plugin.sdk.model.SettingsApplyResultParcel
import com.weartak.plugin.sdk.model.SettingsSchemaParcel
import com.weartak.plugin.sdk.model.SettingsValidationErrorParcel
import com.weartak.plugin.sdk.v2.aidl.IWearTakPluginHostControlV2
import com.weartak.plugin.sdk.v3.aidl.IWearTakPluginHostControlV3

class WearTakPluginService : Service() {
    private val lifecycle = PluginLifecycleMachine()
    private val binder = PluginBinder()

    override fun onBind(intent: Intent?): IBinder {
        lifecycle.dispatch(PluginLifecycleEvent.BIND_ATTACHED)
        return binder
    }

    override fun onDestroy() {
        lifecycle.dispatch(PluginLifecycleEvent.RESET)
        super.onDestroy()
    }

    private inner class PluginBinder : IWearTakPlugin.Stub() {
        private var hostCallback: IWearTakHostCallback? = null

        override fun getPluginInfo() = PluginInfoParcel(
            pluginId = BuildConfig.APPLICATION_ID,
            displayName = "GoTenna",
            versionName = BuildConfig.VERSION_NAME,
            packageName = BuildConfig.APPLICATION_ID,
            description = "WearTAK plugin integration foundation for goTenna radios.",
        )

        override fun getCapabilities() = PluginCapabilitiesParcel(
            hostedMainUi = true,
            externalMainActivity = false,
        )

        override fun getApiVersion() = WearTakPluginContract.CONTRACT_API_VERSION

        override fun getStatus() = PluginStatusParcel(
            state = lifecycle.snapshot(),
            message = GoTennaRadioIntegration.status().message,
        )

        override fun initializePlugin(init: PluginInitParcel?, control: IWearTakPluginControl?) {
            initializePluginV2(init, control, null)
        }

        override fun initializePluginV2(
            init: PluginInitParcel?,
            control: IWearTakPluginControl?,
            controlV2: IWearTakPluginHostControlV2?,
        ) {
            lifecycle.dispatch(PluginLifecycleEvent.INITIALIZED)
            notifyStatus()
        }

        override fun initializePluginV3(
            init: PluginInitParcel?,
            control: IWearTakPluginControl?,
            controlV2: IWearTakPluginHostControlV2?,
            controlV3: IWearTakPluginHostControlV3?,
        ) {
            initializePluginV2(init, control, controlV2)
        }

        override fun startPlugin() {
            lifecycle.dispatch(PluginLifecycleEvent.HOST_STARTED)
            notifyStatus()
        }

        override fun stopPlugin() {
            lifecycle.dispatch(PluginLifecycleEvent.HOST_STOPPED)
            notifyStatus()
        }

        override fun shutdownPlugin() {
            lifecycle.dispatch(PluginLifecycleEvent.HOST_SHUTDOWN)
            notifyStatus()
            hostCallback = null
        }

        override fun registerHostCallback(callback: IWearTakHostCallback?) {
            hostCallback = callback
            lifecycle.dispatch(PluginLifecycleEvent.HOST_CALLBACK_REGISTERED)
            notifyStatus()
        }

        override fun unregisterHostCallback(callback: IWearTakHostCallback?) {
            if (hostCallback === callback) hostCallback = null
        }

        override fun getSettingsSchema() = SettingsSchemaParcel()

        override fun getSettingsValues() = Bundle()

        override fun applySettings(values: Bundle?) {
            if (values != null && values.size() > 0) {
                notifyError("This integration does not define plugin settings.")
            }
        }

        override fun applySettingsWithResult(values: Bundle?, applyMode: Int): SettingsApplyResultParcel {
            val errors = values?.keySet()?.map { fieldId ->
                SettingsValidationErrorParcel(
                    fieldId = fieldId,
                    code = "UNSUPPORTED_FIELD",
                    message = "This integration does not define plugin settings.",
                )
            }.orEmpty()
            return SettingsApplyResultParcel(
                success = errors.isEmpty(),
                applyMode = applyMode,
                values = Bundle(),
                restartRequired = false,
                anyValueChanged = false,
                errors = errors,
                hostDerivedFieldIds = emptyList(),
            )
        }

        override fun onHostSettingsChanged(hostSettings: HostSettingsParcel?) = Unit

        override fun getMainUiSchema() = PluginMainUiSchemaParcel(
            cards = listOf(
                MainUiCardParcel(
                    cardType = MainUiCardTypes.STATUS,
                    cardId = "radio_status",
                    title = "Radio unavailable",
                    subtitle = GoTennaRadioIntegration.status().message,
                ),
                MainUiCardParcel(
                    cardType = MainUiCardTypes.ACTION,
                    cardId = "refresh_status",
                    title = "Status",
                    content = MainUiActionContract.createContent(
                        actionId = ACTION_REFRESH_STATUS,
                        actionLabel = "Refresh status",
                        enabled = !lifecycle.isShutdown(),
                    ),
                ),
            ),
        )

        override fun getMainUiState() = Bundle().apply {
            val status = GoTennaRadioIntegration.status()
            putBoolean("radio_connected", status.connected)
            putString("radio_status", status.message)
        }

        override fun invokeMainUiAction(actionId: String?, args: Bundle?) {
            if (lifecycle.isShutdown()) {
                notifyError("Plugin has shut down.", PluginErrorCodes.ILLEGAL_STATE)
                return
            }
            if (actionId != ACTION_REFRESH_STATUS) {
                notifyError("Unknown GoTenna action. Radio controls are not implemented.")
                return
            }
            notifyStatus()
        }

        private fun notifyStatus() {
            try {
                hostCallback?.onPluginStatusChanged(getStatus())
            } catch (error: RemoteException) {
                Log.w(TAG, "Unable to notify WearTAK host of plugin status", error)
            }
            try {
                hostCallback?.onPluginMainUiStateChanged()
            } catch (error: RemoteException) {
                Log.w(TAG, "Unable to notify WearTAK host of refreshed UI state", error)
            }
        }

        private fun notifyError(message: String, code: Int = PluginErrorCodes.INVALID_ARGUMENT) {
            Log.w(TAG, message)
            try {
                hostCallback?.onPluginError(
                    PluginErrorParcel(
                        code = code,
                        message = message,
                        fatal = false,
                    ),
                )
            } catch (error: RemoteException) {
                Log.w(TAG, "Unable to report plugin error to WearTAK host", error)
            }
        }
    }

    companion object {
        const val ACTION_REFRESH_STATUS = "gotenna.refresh"
        private const val TAG = "GoTennaWearTakPlugin"
    }
}
