package com.weartak.plugin.gotenna

data class RadioIntegrationStatus(
    val connected: Boolean,
    val message: String,
)

object GoTennaRadioIntegration {
    fun status(): RadioIntegrationStatus = RadioIntegrationStatus(
        connected = false,
        message = "Radio transport is not implemented. A supported goTenna SDK or protocol specification is required.",
    )
}
