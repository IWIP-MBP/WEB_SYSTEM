# 员工花名册 Excel 导入规范与填写要求
# Petunjuk & Persyaratan Pengisian Impor Data Karyawan (Excel)

> **适用于 / Berlaku untuk**: ACC5 企业人事管理系统 (Sistem Manajemen SDM ACC5)  
> **核心数据格式标准 / Standar Format Nilai Data**: **【印尼文在前 + 空格 + 中文在后】(Bahasa Indonesia [spasi] Bahasa Mandarin)**  
> **支持文件格式 / Format Berkas**: `.xlsx` / `.xls` (Microsoft Excel)  

---

## ⭐️ 核心规范原则：印尼文在前 + 空格 + 中文在后
## Prinsip Utama: Bahasa Indonesia di Depan + Spasi + Bahasa Mandarin di Belakang

在工厂园区管理与数据库底账规范中，**车间、班组、性别、国籍、宗教**等核心分类字段，**必须严格按照【印尼文 + 1个空格 + 中文】的标准化组合录入**，以确保中印双方无缝沟通及系统算法精准对账！

Dalam standarisasi sistem HR dan database operasional pabrik, nilai data pada kolom seperti **Bengkel (车间), Grup (班组), JK/Jenis Kelamin (性别), Kewarganegaraan (国籍), dan Agama (宗教)** **WAJIB menggunakan format standar: [Bahasa Indonesia] [spasi] [Bahasa Mandarin]**.

---

## 一、各字段标准填写规范与双语对照表
## I. Tabel Rincian Kolom & Standar Pengisian (Bilingual)

| 序号 <br> No | 表头列名 <br> (支持中/印/中印复合) | 是否必填 <br> Wajib/Opsional | 推荐格式 <br> Format | 标准填写值范例 <br> **【印尼文 + 空格 + 中文】** | 填写规则与系统约束说明 <br> Aturan & Penjelasan Sistem |
| :---: | :--- | :---: | :---: | :--- | :--- |
| **1** | **ID 工号** <br> `工号` / `ID Nomor` / `ID` | **必填 <br> (Wajib)** | 纯文本 <br> (Teks) | `26001088` / `A0588` | **员工唯一标识码**。工号不可重复且不可为空。若工号在系统中已存在，系统自动**覆盖更新**老档案；若无则**新增入职**。<br>*Identitas unik karyawan. Wajib diisi. Jika ID sudah ada di database, data lama akan diperbarui secara otomatis.* |
| **2** | **Nama 姓名** <br> `姓名` / `Nama` | **必填 <br> (Wajib)** | 文本 <br> (Teks) | `Agus Santoso` / `张伟` | **员工全名**。工号或姓名为空的行，系统将自动跳过不导入。<br>*Nama lengkap karyawan. Baris akan dilewati jika ID atau Nama kosong.* |
| **3** | **Bengkel 车间** <br> `车间` / `Bengkel` | 建议填写 <br> (Disarankan) | 文本 <br> (Teks) | **`ACC5 综合管理部`** <br> `kantin 食堂` <br> `Akomodasi 宿管` <br> `Gudang 物资` <br> `Transportasi 车队` <br> `Perbaikan 维修` <br> `General Affair 综合` | **必须按【印尼文 + 空格 + 中文】填写**。<br>请全厂统一命名，不要漏写中文或印尼文，否则会导致组织架构与部门统计分散。<br>*Format wajib: **[Nama Bengkel ID] [spasi] [Nama Bengkel CN]**. Harap seragam agar struktur organisasi rapi.* |
| **4** | **Grup 班组** <br> `班组` / `Grup` / `Regu` | 选填 <br> (Opsional) | 文本 <br> (Teks) | `KANTIN RESTO 小炒食堂` <br> `Apartment Loyploy IND 路易公寓印尼生活区` <br> `Regu 1 一班` / `Regu A 甲班` | **建议按【印尼文 + 空格 + 中文】填写**。<br>员工所在具体班组或生产作业单元。<br>*Regu atau tim shift kerja karyawan.* |
| **5** | **JK 性别** <br> `性别` / `JK` / `Jenis Kelamin` | 建议填写 <br> (Disarankan) | 文本 <br> (Teks) | **`Laki Laki 男`** 或 **`Laki-laki 男`** <br> **`Perempuan 女`** | **必须按【印尼文 + 空格 + 中文】填写**。<br>男员工填写 `Laki Laki 男`，女员工填写 `Perempuan 女`。<br>*Wajib format: `Laki Laki 男` untuk pria, dan `Perempuan 女` untuk wanita.* |
| **6** | **Negara 国籍** <br> `国籍` / `Negara` / `Kewarganegaraan` | **关键项** <br> (Sangat Penting) | 文本 <br> (Teks) | **`IND 印尼籍`** <br> **`China 中国籍`** | **必须按【印尼文 + 空格 + 中文】填写**。<br>系统数据大盘中的**本土化率 (Rasio Lokalisasi)** 核心指标依据此字段自动核算。印尼本地籍填 `IND 印尼籍`，中方员工填 `China 中国籍`。<br>*Sangat penting untuk penghitungan otomatis Rasio Lokalisasi.* |
| **7** | **Agama 宗教** <br> `宗教` / `Agama` | 选填 <br> (Opsional) | 文本 <br> (Teks) | **`islam 伊斯兰`** <br> **`Kristen 基督教`** <br> **`Katholik 天主教`** <br> **`budha 佛教`** | **按【印尼文 + 空格 + 中文】填写**。<br>印尼本地员工宗教背景，便于开斋节等节假日及工伤福利统筹。<br>*Format standar agama tenaga kerja lokal Indonesia.* |
| **8** | **Jabatan (CN) 岗位(中)** <br> `岗位(中)` / `Jabatan (CN)` | 选填 <br> (Opsional) | 文本 <br> (Teks) | `安全员` / `人事专员` / `司机` / `清洁` | 员工中文岗位名称，在系统切换为中文界面时优先展示。<br>*Nama jabatan dalam Bahasa Mandarin.* |
| **9** | **Jabatan (ID) 岗位(印)** <br> `岗位(印)` / `Jabatan (ID)` | 选填 <br> (Opsional) | 文本 <br> (Teks) | `Safety Officer` / `Staff HR` / `Driver` / `Translator` | 员工印尼文岗位名称，在系统切换为印尼语界面时优先展示。<br>*Nama jabatan dalam Bahasa Indonesia.* |
| **10** | **Nomor KTP 身份证号** <br> `身份证号` / `Nomor KTP` / `ID Card` | 建议填写 <br> (Disarankan) | **纯文本** <br> **(Teks)** | `'7306051508980001` <br> `'320101199001011234` | ⚠️ **防错警告**：必须将 Excel 单元格设为【文本格式】，防止 16 位 KTP 或 18 位身份证因数值过长被转换为科学计数法导致末尾几位全变成 0。<br>*Wajib format sel **TEXT** agar digit KTP tidak berubah menjadi nol.* |
| **11** | **Tanggal Masuk 入职日期** <br> `入职日期` / `Tgl Masuk` / `Tanggal Masuk` | 建议填写 <br> (Disarankan) | 日期文本 <br> `YYYY-MM-DD` | `2026-08-01` | **统一格式：YYYY-MM-DD (年-月-日)**。请勿使用 `2026/8/1` 或 `01-08-2026`。<br>*Wajib format: `YYYY-MM-DD` (contoh: `2026-08-01`).* |
| **12** | **Tanggal Lahir 出生日期** <br> `出生日期` / `Tgl Lahir` / `Tanggal Lahir` | 选填 <br> (Opsional) | 日期文本 <br> `YYYY-MM-DD` | `1995-05-20` | 用于生日关怀提醒与年龄结构分析。格式：`YYYY-MM-DD`。<br>*Untuk pengingat ulang tahun dan analisis demografi usia.* |
| **13** | **Kontrak Berakhir 合同到期日** <br> `合同到期日` / `Kontrak Berakhir` | 选填 <br> (Opsional) | 日期文本 <br> `YYYY-MM-DD` | `2027-07-31` | 合同截止日期，用于续签预警。格式：`YYYY-MM-DD`。<br>*Tanggal masa berlaku kontrak kerja.* |
| **14** | **Perusahaan 归属公司** <br> `归属公司` / `Perusahaan` | 选填 <br> (Opsional) | 文本 <br> (Teks) | `IWIP` / `ACC5直属` / `外协承包单位` | 员工归属用人单位或外包公司，支持按公司进行独立人员筛选。<br>*Perusahaan penempatan kerja.* |
| **15** | **Keterangan 备注** <br> `备注` / `Keterangan` | 选填 <br> (Opsional) | 文本 <br> (Teks) | `特殊工种/持证特种作业` | 补充说明信息。<br>*Catatan tambahan.* |

---

## 二、标准模板填写示例（完全对应系统数据库格式）
## II. Contoh Format Isian Standar Excel (Sesuai Database Sistem)

请参考下表直接在 Excel 中填报：

| ID 工号 | Nama 姓名 | Bengkel 车间 | Grup 班组 | JK 性别 | Negara 国籍 | Agama 宗教 | Jabatan (CN) | Jabatan (ID) | Nomor KTP 身份证号 | Tanggal Masuk 入职日期 | Perusahaan 归属公司 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `8260420046` | Yuliana Papilaya | `kantin 食堂` | `KANTIN RESTO 小炒食堂` | `Perempuan 女` | `IND 印尼籍` | `islam 伊斯兰` | 厨师 | Cook | `'7306055508980001` | `2024-04-20` | IWIP |
| `6260702014` | Syin Men | `Akomodasi 宿管` | `Apartment Loyploy IND 路易公寓印尼生活区` | `Laki Laki 男` | `China 中国籍` | `0` | 翻译 | Translator | `'320102199207021234` | `2024-07-02` | IWIP |
| `8260914023` | Hermelina Nuha | `ACC5 综合管理部` | `Regu 1 一班` | `Perempuan 女` | `IND 印尼籍` | `Kristen 基督教` | 文员 | Staff Admin | `'7306054809950002` | `2025-09-14` | ACC5直属 |
| `8260906002` | Krismawati Djorebe | `Transportasi 车队` | `Regu A 甲班` | `Laki Laki 男` | `IND 印尼籍` | `Katholik 天主教` | 司机 | Driver | `'7306051206960003` | `2025-09-06` | IWIP |

---

## 三、避坑要点提示
## III. Catatan Penting Pencegahan Kesalahan

1. **组合格式规范**：在填写车间、班组、性别、国籍、宗教时，中间必须是**单个空格**，如 `Laki Laki 男`、`Perempuan 女`、`IND 印尼籍`、`China 中国籍`、`kantin 食堂`。
2. **身份证号防截断**：输入纯数字身份证前先将单元格改为**“文本”**，或在最前面加英文单引号 `'`。
3. **日期格式标准**：年-月-日之间必须使用减号 `-` 连接，例如 `2026-08-01`。
4. **覆盖更新机制**：工号相同的老员工会自动更新为 Excel 中的最新车间和岗位信息，不会丢失以往的历史考勤和领用记录。
