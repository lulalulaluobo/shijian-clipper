import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.gradle.api.GradleException

val releaseStoreFile = providers.environmentVariable("SHIJIAN_RELEASE_STORE_FILE").orNull
val releaseStorePassword = providers.environmentVariable("SHIJIAN_RELEASE_STORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("SHIJIAN_RELEASE_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("SHIJIAN_RELEASE_KEY_PASSWORD").orNull
val releaseSigningReady = listOf(releaseStoreFile, releaseStorePassword, releaseKeyAlias, releaseKeyPassword).all { !it.isNullOrBlank() }
val requestedReleaseTask = gradle.startParameter.taskNames.any { it.contains("release", ignoreCase = true) }


plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.lulalulaluobo.wechatclipper"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.lulalulaluobo.wechatclipper"
        minSdk = 26
        targetSdk = 36
        versionCode = 7
        versionName = "1.3.0"

    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        buildConfig = true
    }
    signingConfigs {
        if (releaseSigningReady) {
            create("release") {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }
    buildTypes {
        getByName("release") {
            if (releaseSigningReady) signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.1")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
