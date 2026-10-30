package iq.shaghla.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val Forest = Color(0xFF123B35)
private val Lime = Color(0xFFD7F36A)
private val Paper = Color(0xFFF5F7F4)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ShaghlaApp() }
    }
}

@Composable
fun ShaghlaApp() {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("shaghla", 0) }
    var baseUrl by remember { mutableStateOf(prefs.getString("api_url", "") ?: "") }
    var token by remember { mutableStateOf(prefs.getString("token", "") ?: "") }
    var role by remember { mutableStateOf(prefs.getString("role", "worker") ?: "worker") }
    var phone by remember { mutableStateOf("") }
    var otp by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf("الوظائف") }
    var requested by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var jobs by remember { mutableStateOf<List<ApiJob>>(emptyList()) }
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("أخرى") }
    var area by remember { mutableStateOf("") }
    var wage by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val api = remember(baseUrl, token) { ShaghlaApi(baseUrl, token.takeIf { it.isNotBlank() }) }

    fun runTask(task: suspend () -> Unit) {
        scope.launch {
            busy = true
            message = ""
            try { task() } catch (error: Exception) {
                message = error.message ?: "صار خطأ، حاول مرة ثانية"
            } finally { busy = false }
        }
    }

    fun loadJobs() {
        runTask { jobs = api.jobs(query) }
    }

    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(colorScheme = lightColorScheme(primary = Forest, secondary = Lime)) {
            Scaffold(
                containerColor = Paper,
                bottomBar = {
                    if (token.isNotBlank()) {
                        NavigationBar(containerColor = Color.White) {
                            listOf("الوظائف", "نشر وظيفة", "حسابي").forEach { item ->
                                NavigationBarItem(
                                    selected = tab == item,
                                    onClick = { tab = item; if (item == "الوظائف") loadJobs() },
                                    icon = {},
                                    label = { Text(item) }
                                )
                            }
                        }
                    }
                }
            ) { padding ->
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 18.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item {
                        Spacer(Modifier.height(18.dp))
                        Text("شَغلة", color = Forest, fontSize = 32.sp, fontWeight = FontWeight.Black)
                        Text("شغلك أقرب إلك.", color = Forest.copy(alpha = .7f))
                        Spacer(Modifier.height(8.dp))
                        if (message.isNotBlank()) {
                            Text(message, color = Color(0xFFB3261E), fontWeight = FontWeight.Medium)
                        }
                        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Forest)
                    }

                    if (token.isBlank()) {
                        item {
                            Text("خلّينا نوصلك بفرصة عمل", color = Forest, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                            Text("أدخل رابط خادم شَغلة المنشور عبر HTTPS.")
                            OutlinedTextField(
                                value = baseUrl, onValueChange = { baseUrl = it; prefs.edit().putString("api_url", it).apply() },
                                modifier = Modifier.fillMaxWidth(), label = { Text("رابط API") },
                                placeholder = { Text("https://api.example.com") }, singleLine = true
                            )
                            OutlinedTextField(
                                value = phone, onValueChange = { phone = it },
                                modifier = Modifier.fillMaxWidth(), label = { Text("رقم الهاتف العراقي") },
                                placeholder = { Text("07xxxxxxxxx") }, singleLine = true
                            )
                            Text("نوع الحساب", color = Forest, fontWeight = FontWeight.Bold)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                FilterChip(selected = role == "worker", onClick = { role = "worker" }, label = { Text("باحث عن عمل") })
                                Spacer(Modifier.width(8.dp))
                                FilterChip(selected = role == "employer", onClick = { role = "employer" }, label = { Text("صاحب عمل") })
                            }
                            if (!requested) {
                                Button(
                                    onClick = {
                                        runTask {
                                            api.requestOtp(phone, role)
                                            requested = true
                                            message = "إذا كان الرقم صحيحاً، راح توصلك رسالة برمز التحقق."
                                        }
                                    },
                                    enabled = !busy && baseUrl.isNotBlank() && phone.isNotBlank(),
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("إرسال رمز التحقق") }
                            } else {
                                OutlinedTextField(
                                    value = otp, onValueChange = { otp = it.filter(Char::isDigit).take(6) },
                                    modifier = Modifier.fillMaxWidth(), label = { Text("رمز التحقق المكوّن من 6 أرقام") },
                                    singleLine = true
                                )
                                Button(
                                    onClick = {
                                        runTask {
                                            val result = api.verifyOtp(phone, otp)
                                            token = result.first
                                            prefs.edit().putString("token", token).putString("role", role).apply()
                                            requested = false
                                            message = "تم تسجيل الدخول بنجاح"
                                            jobs = api.jobs()
                                        }
                                    },
                                    enabled = !busy && otp.length == 6,
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("تأكيد وتسجيل الدخول") }
                                TextButton(onClick = { requested = false; otp = "" }) { Text("تغيير الرقم") }
                            }
                            Text("ملاحظة: تسجيل الدخول يحتاج خادماً منشوراً ومزود SMS فعلياً.", color = Color.Gray, fontSize = 12.sp)
                        }
                    } else {
                        when (tab) {
                            "الوظائف" -> {
                                item {
                                    Text("اكتشف فرص العمل", color = Forest, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                                    OutlinedTextField(
                                        value = query, onValueChange = { query = it },
                                        modifier = Modifier.fillMaxWidth(), label = { Text("ابحث عن وظيفة") },
                                        singleLine = true
                                    )
                                    Button(onClick = { loadJobs() }, modifier = Modifier.fillMaxWidth(), enabled = !busy) {
                                        Text("بحث وتحديث الوظائف")
                                    }
                                }
                                if (jobs.isEmpty()) item { Text("ماكو وظائف معروضة حالياً. حدّث القائمة أو جرّب البحث.") }
                                items(jobs, key = { it.id }) { job ->
                                    Card(
                                        modifier = Modifier.fillMaxWidth(),
                                        colors = CardDefaults.cardColors(containerColor = Color.White),
                                        shape = RoundedCornerShape(18.dp)
                                    ) {
                                        Column(Modifier.padding(16.dp)) {
                                            Text(job.title, color = Forest, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                                            Text("${job.governorate} • ${job.area} • ${job.category}", color = Color.DarkGray)
                                            Spacer(Modifier.height(6.dp))
                                            Text(if (job.wageIqd > 0) "${job.wageIqd} د.ع" else "الأجر حسب الاتفاق", color = Forest, fontWeight = FontWeight.Bold)
                                            Text(job.workType, color = Color.Gray)
                                            if (role == "worker") {
                                                Button(onClick = {
                                                    runTask { api.apply(job.id); message = "تم إرسال طلبك بنجاح" }
                                                }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("قدّم على الوظيفة") }
                                            }
                                        }
                                    }
                                }
                            }
                            "نشر وظيفة" -> {
                                item {
                                    Text("انشر فرصة عمل", color = Forest, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                                    if (role != "employer") {
                                        Text("هذه الخدمة مخصصة لحسابات أصحاب العمل.")
                                    } else {
                                        OutlinedTextField(title, { title = it }, Modifier.fillMaxWidth(), label = { Text("عنوان الوظيفة") })
                                        OutlinedTextField(description, { description = it }, Modifier.fillMaxWidth(), label = { Text("تفاصيل الوظيفة") }, minLines = 3)
                                        OutlinedTextField(category, { category = it }, Modifier.fillMaxWidth(), label = { Text("التصنيف") })
                                        OutlinedTextField(area, { area = it }, Modifier.fillMaxWidth(), label = { Text("المنطقة داخل المحافظة") })
                                        OutlinedTextField(wage, { wage = it.filter(Char::isDigit) }, Modifier.fillMaxWidth(), label = { Text("الأجر بالدينار العراقي") })
                                        Button(
                                            onClick = {
                                                runTask {
                                                    api.createJob(title, description, category, "كركوك", area, wage.toIntOrNull() ?: 0, "يومي")
                                                    title = ""; description = ""; wage = ""
                                                    message = "تم نشر الوظيفة بنجاح"
                                                    tab = "الوظائف"; jobs = api.jobs()
                                                }
                                            },
                                            enabled = !busy && title.length >= 3,
                                            modifier = Modifier.fillMaxWidth()
                                        ) { Text("نشر الوظيفة") }
                                    }
                                }
                            }
                            else -> item {
                                Text("حسابك في شَغلة", color = Forest, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                                Text("نوع الحساب: ${if (role == "worker") "باحث عن عمل" else "صاحب عمل"}")
                                Text("رقم الهاتف: $phone")
                                OutlinedButton(
                                    onClick = {
                                        token = ""; prefs.edit().remove("token").apply()
                                        requested = false; otp = ""; jobs = emptyList()
                                        message = "تم تسجيل الخروج"
                                    },
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("تسجيل الخروج") }
                            }
                        }
                    }
                    item {
                        Spacer(Modifier.height(20.dp))
                        Text("تنبيه أمان: لا تدفع أي مبلغ مقابل الحصول على وظيفة أو مقابلة.", color = Forest)
                        Spacer(Modifier.height(24.dp))
                    }
                }
            }
        }
    }
}
