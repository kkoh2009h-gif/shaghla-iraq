package iq.shaghla.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Forest = Color(0xFF123B35)
private val Lime = Color(0xFFD7F36A)
private val Paper = Color(0xFFF5F7F4)

data class Job(val title: String, val company: String, val area: String, val pay: String, val type: String)
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ShaghlaApp() }
    }
}

@Composable
fun ShaghlaApp() {
    var tab by remember { mutableStateOf("الرئيسية") }
    var query by remember { mutableStateOf("") }
    val jobs = listOf(
        Job("عامل مخزن", "شركة تجارية", "كركوك - طريق بغداد", "25,000 د.ع / يوم", "يومي"),
        Job("موظف مبيعات", "متجر الرافدين", "كركوك - المركز", "500,000 د.ع / شهر", "شهري"),
        Job("فني صيانة حاسوب", "مركز تقني", "كركوك - شوراو", "حسب الاتفاق", "دوام جزئي")
    )
    MaterialTheme {
        Scaffold(containerColor = Paper, bottomBar = {
            NavigationBar(containerColor = Color.White) {
                listOf("الرئيسية", "الوظائف", "المحفوظات", "حسابي").forEach {
                    NavigationBarItem(selected = tab == it, onClick = { tab = it }, icon = {}, label = { Text(it) })
                }
            }
        }) { padding ->
            LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 18.dp)) {
                item {
                    Spacer(Modifier.height(18.dp))
                    Text("شَغلة", color = Forest, fontSize = 32.sp, fontWeight = FontWeight.Black)
                    Text("شغلك أقرب إلك.", color = Forest.copy(alpha = .7f))
                    Spacer(Modifier.height(18.dp))
                    Card(colors = CardDefaults.cardColors(containerColor = Forest), shape = RoundedCornerShape(24.dp)) {
                        Column(Modifier.padding(20.dp)) {
                            Text("فرصتك الجاية تبدأ من هنا", color = Lime, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                            Text("منصة تجمع أصحاب العمل والباحثين عن عمل في العراق", color = Color.White)
                            Spacer(Modifier.height(16.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { tab = "الوظائف" }, colors = ButtonDefaults.buttonColors(containerColor = Lime, contentColor = Forest)) { Text("أريد شغل") }
                                OutlinedButton(onClick = { tab = "حسابي" }, colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)) { Text("أحتاج عمّال") }
                            }
                        }
                    }
                    Spacer(Modifier.height(18.dp))
                    OutlinedTextField(value = query, onValueChange = { query = it }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("ابحث عن وظيفة أو مهنة") }, singleLine = true, shape = RoundedCornerShape(16.dp))
                    Spacer(Modifier.height(18.dp))
                    Text(if (tab == "الرئيسية") "أحدث فرص العمل" else tab, fontSize = 21.sp, color = Forest, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(8.dp))
                }
                items(jobs.filter { it.title.contains(query, true) || it.company.contains(query, true) }) { job ->
                    Card(Modifier.fillMaxWidth().padding(vertical = 6.dp), colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(18.dp)) {
                        Column(Modifier.padding(16.dp)) {
                            Text(job.title, color = Forest, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                            Text(job.company + " • " + job.area, color = Color.DarkGray)
                            Spacer(Modifier.height(8.dp))
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                                Text(job.pay, color = Forest, fontWeight = FontWeight.Bold)
                                Surface(color = Lime.copy(alpha = .45f), shape = RoundedCornerShape(50)) { Text(job.type, Modifier.padding(horizontal = 12.dp, vertical = 5.dp), color = Forest) }
                            }
                            Spacer(Modifier.height(8.dp))
                            Text("إعلان تجريبي للعرض — غير متاح للتقديم حالياً", color = Color.Gray, fontSize = 12.sp)
                        }
                    }
                }
                item { Spacer(Modifier.height(20.dp)); Text("تنبيه أمان: لا تدفع أي مبلغ مقابل الحصول على وظيفة أو مقابلة.", color = Forest, fontWeight = FontWeight.Medium); Spacer(Modifier.height(24.dp)) }
            }
        }
    }
}
