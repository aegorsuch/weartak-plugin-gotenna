package com.weartak.plugin.gotenna

import android.content.Intent
import android.os.Bundle
import com.weartak.plugin.sdk.MainUiActionContract
import com.weartak.plugin.sdk.aidl.IWearTakPlugin
import com.weartak.plugin.sdk.aidl.IWearTakHostCallback
import com.weartak.plugin.sdk.model.CotReadyEventParcel
import com.weartak.plugin.sdk.model.MainUiCardTypes
import com.weartak.plugin.sdk.model.PluginErrorCodes
import com.weartak.plugin.sdk.model.PluginErrorParcel
import com.weartak.plugin.sdk.model.PluginLifecycleState
import com.weartak.plugin.sdk.model.PluginStatusParcel
import com.weartak.plugin.sdk.model.SensorEventParcel
import com.weartak.plugin.sdk.model.SharedBufferParcel
import com.weartak.plugin.sdk.validation.ContractValidationResult
import com.weartak.plugin.sdk.validation.MainUiSchemaContractValidator
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GoTennaRadioIntegrationTest {
    @Test
    fun statusDoesNotClaimConnectionBeforeTransportExists() {
        val status = GoTennaRadioIntegration.status()

        assertFalse(status.connected)
        assertTrue(status.message.contains("not implemented"))
        assertTrue(status.message.contains("SDK or protocol specification"))
    }

    @Test
    fun pluginBinderAdvertisesOnlyImplementedCapabilities() {
        val service = Robolectric.buildService(WearTakPluginService::class.java).create().get()
        try {
            val plugin = IWearTakPlugin.Stub.asInterface(service.onBind(Intent()))

            assertNotNull(plugin.pluginInfo)
            assertEquals("goTenna", plugin.pluginInfo.displayName)
            assertTrue(plugin.capabilities.hostedMainUi)
            assertFalse(plugin.capabilities.externalMainActivity)
            assertFalse(plugin.capabilities.deviceIntegration)
            assertTrue(plugin.status.message.contains("not implemented"))

            plugin.initializePluginV2(null, null, null)
            plugin.startPlugin()
            assertEquals(PluginLifecycleState.RUNNING, plugin.status.state)
            assertFalse(plugin.status.message.contains("connected"))

            val settingsResult = plugin.applySettingsWithResult(
                Bundle().apply { putString("unexpected", "value") },
                0,
            )
            assertFalse(settingsResult.success)
            assertEquals("unexpected", settingsResult.errors.single().fieldId)
        } finally {
            service.onDestroy()
        }
    }

    @Test
    fun v3InitializationPreservesHostedStatusWithoutEnablingRadioOrPcm() {
        withPlugin { plugin ->
            plugin.initializePluginV3(null, null, null, null)
            plugin.startPlugin()
            assertEquals(PluginLifecycleState.RUNNING, plugin.status.state)
            assertTrue(plugin.capabilities.hostedMainUi)
            assertFalse(plugin.capabilities.deviceIntegration)
            assertFalse(plugin.mainUiState.getBoolean("radio_connected"))
        }
    }

    @Test
    fun hostedSchemaProvidesRadioStatusWithoutExternalActivity() {
        withPlugin { plugin ->
            val schema = plugin.mainUiSchema
            assertTrue(MainUiSchemaContractValidator.validate(schema, true) is ContractValidationResult.Ok)
            val statusCard = schema.cards.first()
            assertEquals(MainUiCardTypes.STATUS, statusCard.cardType)
            assertTrue(statusCard.subtitle.orEmpty().contains("not implemented"))
            assertFalse(plugin.mainUiState.getBoolean("radio_connected"))
            val launcher = serviceIntent(android.content.Intent.ACTION_MAIN).apply {
                addCategory(android.content.Intent.CATEGORY_LAUNCHER)
            }
            assertTrue(
                org.robolectric.RuntimeEnvironment.getApplication().packageManager
                    .queryIntentActivities(launcher, 0).isEmpty(),
            )
        }
    }

    @Test
    fun refreshNotifiesHostWithoutClaimingRadioConnection() {
        withPlugin { plugin ->
            val callback = RecordingHostCallback()
            plugin.registerHostCallback(callback)
            val initialStatuses = callback.statusChanges
            val initialUiChanges = callback.mainUiChanges
            val card = plugin.mainUiSchema.cards.single { it.cardType == MainUiCardTypes.ACTION }
            val action = MainUiActionContract.parseContent(card.content).toResult().getOrThrow()
            assertEquals("gotenna.refresh", action.actionId)
            assertEquals("Refresh status", action.actionLabel)
            assertTrue(action.enabled)
            assertEquals(0, action.args.size())
            assertEquals(initialStatuses, callback.statusChanges)
            assertEquals(initialUiChanges, callback.mainUiChanges)
            plugin.invokeMainUiAction(action.actionId, action.args)
            assertEquals(initialUiChanges + 1, callback.mainUiChanges)
            assertEquals(initialStatuses + 1, callback.statusChanges)
            assertTrue(callback.errors.isEmpty())
            assertFalse(plugin.mainUiState.getBoolean("radio_connected"))
        }
    }

    @Test
    fun unknownActionReportsErrorWithoutRefreshingUi() {
        withPlugin { plugin ->
            val callback = RecordingHostCallback()
            plugin.registerHostCallback(callback)
            val initialUiChanges = callback.mainUiChanges
            plugin.invokeMainUiAction("radio.connect", Bundle())
            assertEquals(PluginErrorCodes.INVALID_ARGUMENT, callback.errors.single().code)
            assertEquals(initialUiChanges, callback.mainUiChanges)
        }
    }

    @Test
    fun refreshAfterShutdownDoesNotNotifyUi() {
        withPlugin { plugin ->
            val callback = RecordingHostCallback()
            plugin.registerHostCallback(callback)
            plugin.shutdownPlugin()
            val initialUiChanges = callback.mainUiChanges
            val card = plugin.mainUiSchema.cards.single { it.cardType == MainUiCardTypes.ACTION }
            val action = MainUiActionContract.parseContent(card.content).toResult().getOrThrow()
            assertFalse(action.enabled)
            plugin.invokeMainUiAction(WearTakPluginService.ACTION_REFRESH_STATUS, Bundle())
            assertEquals(initialUiChanges, callback.mainUiChanges)
            assertEquals(PluginLifecycleState.SHUTDOWN, plugin.status.state)
        }
    }

    private fun serviceIntent(action: String) = Intent(action).setPackage(BuildConfig.APPLICATION_ID)

    private fun withPlugin(block: (IWearTakPlugin) -> Unit) {
        val service = Robolectric.buildService(WearTakPluginService::class.java).create().get()
        try {
            block(IWearTakPlugin.Stub.asInterface(service.onBind(Intent())))
        } finally {
            service.onDestroy()
        }
    }

    private class RecordingHostCallback : IWearTakHostCallback.Stub() {
        var mainUiChanges = 0
        var statusChanges = 0
        val errors = mutableListOf<PluginErrorParcel>()

        override fun onPluginMainUiStateChanged() { mainUiChanges++ }
        override fun onPluginStatusChanged(status: PluginStatusParcel?) { statusChanges++ }
        override fun onPluginError(error: PluginErrorParcel) { errors += error }
        override fun onSensorEvent(event: SensorEventParcel?) = Unit
        override fun onSensorBatchEvent(events: MutableList<SensorEventParcel>?) = Unit
        override fun onCotReadyEvent(event: CotReadyEventParcel?) = Unit
        override fun onPluginSettingsSchemaChanged() = Unit
        override fun onPluginSettingsValuesChanged() = Unit
        override fun onPluginMainUiSchemaChanged() = Unit
        override fun onSharedBufferAvailable(buffer: SharedBufferParcel?) = Unit
    }
}
