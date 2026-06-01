package com.hanstock.app.bridge

import android.webkit.JavascriptInterface
import android.widget.Toast
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.hanstock.app.MainActivity

class WebAppInterface(private val activity: MainActivity) {

    // Lazily initialize EncryptedSharedPreferences for hardware-backed secure storage
    private val sharedPreferences by lazy {
        val masterKey = MasterKey.Builder(activity)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        
        EncryptedSharedPreferences.create(
            activity,
            "secure_tokens",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    /**
     * Show a native Android toast from the WebView.
     */
    @JavascriptInterface
    fun showToast(message: String) {
        activity.runOnUiThread {
            Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Securely saves a credential token (e.g., KIS API key, secret, or account token) inside EncryptedSharedPreferences.
     */
    @JavascriptInterface
    fun saveSecureToken(key: String, value: String) {
        sharedPreferences.edit().putString(key, value).apply()
    }

    /**
     * Retrieves a securely saved credential token.
     */
    @JavascriptInterface
    fun getSecureToken(key: String): String {
        return sharedPreferences.getString(key, "") ?: ""
    }

    /**
     * Triggers native biometric authentication. The result will be delivered back to JS
     * via window.onBiometricResult(success) in MainActivity.
     */
    @JavascriptInterface
    fun authenticateBiometric() {
        activity.runOnUiThread {
            activity.showBiometricPrompt()
        }
    }
}
