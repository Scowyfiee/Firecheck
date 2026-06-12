#!/usr/bin/env python3
"""
视频AI智能识别及预警管理系统 - Web管理服务端
Flask + SQLite + Bootstrap + ECharts 数据大屏
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import secrets
import logging
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, jsonify, send_from_directory, g, flash, make_response
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebServer")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "flame_system.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(UPLOAD_DIR / "pictures").mkdir(exist_ok=True)
(UPLOAD_DIR / "videos").mkdir(exist_ok=True)
(UPLOAD_DIR / "logo").mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.executescript("""
CREATE TABLE IF NOT EXISTS T_Site (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT DEFAULT '视频AI智能识别及预警管理系统',
    SiteName TEXT DEFAULT '火焰预警平台',
    Logo TEXT,
    thresh REAL DEFAULT 0.35,
    width REAL DEFAULT 640,
    height REAL DEFAULT 480,
    video_times REAL DEFAULT 5,
    heartBeat REAL DEFAULT 1,
    exception_times REAL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS T_Role (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Description TEXT,
    IsDelete INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS T_Authority (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    RoleId INTEGER NOT NULL,
    Authority TEXT NOT NULL,
    FOREIGN KEY (RoleId) REFERENCES T_Role(Id)
);

CREATE TABLE IF NOT EXISTS T_Branch (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    ParentId INTEGER DEFAULT 0,
    CreateTime TEXT,
    CreateBy INTEGER,
    Remark TEXT
);

CREATE TABLE IF NOT EXISTS T_Area (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Remark TEXT
);

CREATE TABLE IF NOT EXISTS T_User (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Account TEXT UNIQUE,
    Name TEXT NOT NULL,
    AreaId INTEGER,
    BranchId INTEGER,
    Password TEXT NOT NULL,
    CreateTime TEXT,
    CreateBy INTEGER,
    Remark TEXT,
    FOREIGN KEY (BranchId) REFERENCES T_Branch(Id),
    FOREIGN KEY (AreaId) REFERENCES T_Area(Id)
);

CREATE TABLE IF NOT EXISTS T_UserRole (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL,
    RoleId INTEGER NOT NULL,
    IsDefault TEXT DEFAULT 'isdefault',
    CreateTime TEXT,
    IsDeleted TEXT DEFAULT 'undeleted',
    FOREIGN KEY (UserId) REFERENCES T_User(Id),
    FOREIGN KEY (RoleId) REFERENCES T_Role(Id)
);

CREATE TABLE IF NOT EXISTS T_Dictionary (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Key TEXT NOT NULL,
    Value TEXT NOT NULL,
    Remark TEXT
);

CREATE TABLE IF NOT EXISTS T_Device (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    MAC TEXT,
    Longitude TEXT,
    Latitude TEXT,
    Address TEXT,
    AreaId INTEGER,
    ModelPerson TEXT,
    ModelInfo TEXT,
    Maintainer TEXT,
    CreateTime TEXT,
    StructuralInfo TEXT,
    DetailInfo TEXT,
    LastConnectTime TEXT,
    AutoGenerateError TEXT DEFAULT 'no',
    Remark TEXT,
    FOREIGN KEY (AreaId) REFERENCES T_Area(Id)
);

CREATE TABLE IF NOT EXISTS T_Camera (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    IP TEXT,
    MAC TEXT,
    CameraUrl TEXT,
    Name TEXT,
    Longitude TEXT,
    Latitude TEXT,
    AreaId INTEGER,
    Type TEXT,
    InstallTime TEXT,
    BandWidth REAL,
    Maintainer TEXT,
    DeviceId INTEGER,
    Remark TEXT,
    FOREIGN KEY (AreaId) REFERENCES T_Area(Id),
    FOREIGN KEY (DeviceId) REFERENCES T_Device(Id)
);

CREATE TABLE IF NOT EXISTS T_DetectResult (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Longitude TEXT,
    Latitude TEXT,
    Location TEXT,
    Picture TEXT,
    VideoUrl TEXT,
    AreaId INTEGER,
    CreatTime TEXT,
    CameraId INTEGER,
    DeviceId INTEGER,
    Status TEXT DEFAULT '1',
    OperateUserId INTEGER,
    OperateTime TEXT,
    UrgencyDegree TEXT,
    OperateResult TEXT,
    Description TEXT,
    AuditUserId INTEGER,
    AuditTime TEXT,
    Remark TEXT,
    FOREIGN KEY (AreaId) REFERENCES T_Area(Id),
    FOREIGN KEY (CameraId) REFERENCES T_Camera(Id),
    FOREIGN KEY (DeviceId) REFERENCES T_Device(Id),
    FOREIGN KEY (OperateUserId) REFERENCES T_User(Id),
    FOREIGN KEY (AuditUserId) REFERENCES T_User(Id)
);

CREATE TABLE IF NOT EXISTS T_CameraError (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    CameraId INTEGER,
    MAC TEXT,
    CreateTime TEXT,
    ErrorCode TEXT,
    ErrorMsg TEXT,
    Remark TEXT,
    FOREIGN KEY (CameraId) REFERENCES T_Camera(Id)
);

CREATE TABLE IF NOT EXISTS T_DeviceError (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    DeviceId INTEGER,
    MAC TEXT,
    CreateTime TEXT,
    ErrorCode TEXT,
    ErrorMsg TEXT,
    Remark TEXT,
    FOREIGN KEY (DeviceId) REFERENCES T_Device(Id)
);

CREATE TABLE IF NOT EXISTS T_OperateLog (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    MenuName TEXT,
    Type TEXT,
    ContentNew TEXT,
    ContentOld TEXT,
    CreateTime TEXT,
    UserId INTEGER,
    Remark TEXT,
    FOREIGN KEY (UserId) REFERENCES T_User(Id)
);

CREATE TABLE IF NOT EXISTS T_UserLoginLog (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL,
    LoginTime TEXT NOT NULL,
    LoginInIp TEXT,
    LoginType TEXT NOT NULL,
    FOREIGN KEY (UserId) REFERENCES T_User(Id)
);
""")
    db.commit()
    db.close()
    seed_data()


def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()


def seed_data():
    db = sqlite3.connect(str(DB_PATH))
    c = db.execute("SELECT COUNT(*) FROM T_User").fetchone()
    if c and c[0] > 0:
        db.close()
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("INSERT INTO T_Site (Name, SiteName, thresh, width, height, video_times, heartBeat, exception_times) VALUES (?,?,?,?,?,?,?,?)",
               ("视频AI智能识别及预警管理系统", "火焰预警平台", 0.35, 640, 480, 5, 1, 5))

    db.execute("INSERT INTO T_Role (Id, Name, Description) VALUES (1,'超级管理员','系统最高权限')")
    db.execute("INSERT INTO T_Role (Id, Name, Description) VALUES (2,'处理人','事件处理人员')")
    db.execute("INSERT INTO T_Role (Id, Name, Description) VALUES (3,'审核人','事件审核人员')")

    for auth in ["system_config","department","user","role","device","camera","alarm","audit","log","dashboard","dictionary"]:
        db.execute("INSERT INTO T_Authority (RoleId, Authority) VALUES (1,?)", (auth,))
    for auth in ["alarm","camera","device","dashboard"]:
        db.execute("INSERT INTO T_Authority (RoleId, Authority) VALUES (2,?)", (auth,))
    for auth in ["alarm","audit","dashboard"]:
        db.execute("INSERT INTO T_Authority (RoleId, Authority) VALUES (3,?)", (auth,))

    db.execute("INSERT INTO T_Area (Id, Name) VALUES (1,'重庆市'),(2,'北京市'),(3,'上海市'),(4,'广州市'),(5,'成都市')")
    db.execute("INSERT INTO T_Branch (Id, Name, ParentId, CreateTime) VALUES (1,'总公司',0,?),(2,'重庆分公司',1,?),(3,'技术部',1,?),(4,'运维部',1,?)", (now, now, now, now))

    db.execute("INSERT INTO T_User (Id, Account, Name, AreaId, BranchId, Password, CreateTime) VALUES (1,'admin','系统管理员',1,1,?,?)",
               (hash_pwd("123456"), now))
    db.execute("INSERT INTO T_User (Id, Account, Name, AreaId, BranchId, Password, CreateTime) VALUES (2,'chuli001','张处理',1,3,?,?)",
               (hash_pwd("123456"), now))
    db.execute("INSERT INTO T_User (Id, Account, Name, AreaId, BranchId, Password, CreateTime) VALUES (3,'shenhe001','李审核',1,4,?,?)",
               (hash_pwd("123456"), now))

    db.execute("INSERT INTO T_UserRole (UserId, RoleId, IsDefault, CreateTime, IsDeleted) VALUES (1,1,'isdefault',?,'undeleted')", (now,))
    db.execute("INSERT INTO T_UserRole (UserId, RoleId, IsDefault, CreateTime, IsDeleted) VALUES (2,2,'isdefault',?,'undeleted')", (now,))
    db.execute("INSERT INTO T_UserRole (UserId, RoleId, IsDefault, CreateTime, IsDeleted) VALUES (3,3,'isdefault',?,'undeleted')", (now,))

    dict_data = [
        ("AreaType", "重庆市"), ("AreaType", "北京市"), ("AreaType", "上海市"), ("AreaType", "广州市"), ("AreaType", "成都市"),
        ("UrgencyDegree", "一般"), ("UrgencyDegree", "紧急"), ("UrgencyDegree", "非常紧急"),
        ("OperateResult", "已处理"), ("OperateResult", "误报"), ("OperateResult", "待观察"), ("OperateResult", "无需处理"),
        ("CameraType", "海康威视"), ("CameraType", "大华"), ("CameraType", "宇视"), ("CameraType", "其他"),
        ("ErrorCode", "网络故障"), ("ErrorCode", "图像质量差"), ("ErrorCode", "设备离线"),
    ]
    for key, val in dict_data:
        db.execute("INSERT INTO T_Dictionary (Key, Value) VALUES (?,?)", (key, val))

    db.execute("INSERT INTO T_Device (Id, MAC, Longitude, Latitude, Address, AreaId, ModelInfo, CreateTime, LastConnectTime) VALUES (1,'AAABBBCCCDDD','106.551556','29.563009','重庆理工大学花溪校区',1,'YOLOv11-Fire',?,?)", (now, now))
    db.execute("INSERT INTO T_Device (Id, MAC, Longitude, Latitude, Address, AreaId, ModelInfo, CreateTime, LastConnectTime) VALUES (2,'EEEFFFGGGHHH','106.542236','29.606703','重庆理工大学杨家坪校区',1,'YOLOv11-Fire',?,?)", (now, now))

    db.execute("INSERT INTO T_Camera (Id, IP, MAC, CameraUrl, Name, Longitude, Latitude, AreaId, Type, DeviceId, InstallTime) VALUES (1,'192.168.1.101','CAM:AA:BB:CC:01','rtsp://192.168.1.101:554/stream','花溪-教学楼A',?,?,1,'海康威视',1,?)",
               ("106.551556", "29.563009", now))
    db.execute("INSERT INTO T_Camera (Id, IP, MAC, CameraUrl, Name, Longitude, Latitude, AreaId, Type, DeviceId, InstallTime) VALUES (2,'192.168.1.102','CAM:AA:BB:CC:02','rtsp://192.168.1.102:554/stream','花溪-图书馆',?,?,1,'大华',1,?)",
               ("106.552156", "29.564109", now))
    db.execute("INSERT INTO T_Camera (Id, IP, MAC, CameraUrl, Name, Longitude, Latitude, AreaId, Type, DeviceId, InstallTime) VALUES (3,'192.168.1.201','CAM:AA:BB:CC:03','rtsp://192.168.1.201:554/stream','杨家坪-行政楼',?,?,1,'海康威视',2,?)",
               ("106.542236", "29.606703", now))

    db.commit()
    db.close()
    logger.info("Database seeded with initial data")


# --- Auth ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role_id") != 1:
            flash("权限不足")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT u.*, r.Name as RoleName FROM T_User u LEFT JOIN T_UserRole ur ON u.Id=ur.UserId LEFT JOIN T_Role r ON ur.RoleId=r.Id WHERE u.Id=?", (session["user_id"],)).fetchone()


def add_log(menu_name, op_type, content_new, content_old=""):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO T_OperateLog (MenuName, Type, ContentNew, ContentOld, CreateTime, UserId) VALUES (?,?,?,?,?,?)",
               (menu_name, op_type, str(content_new)[:500], str(content_old)[:500], now, session.get("user_id", 0)))
    db.commit()


# --- Routes: Auth ---

@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        account = request.form.get("account", "")
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT u.*, ur.RoleId FROM T_User u LEFT JOIN T_UserRole ur ON u.Id=ur.UserId WHERE u.Account=? AND ur.IsDeleted='undeleted'",
                          (account,)).fetchone()
        if user and user["Password"] == hash_pwd(password):
            session["user_id"] = user["Id"]
            session["user_name"] = user["Name"]
            session["role_id"] = user["RoleId"]
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute("INSERT INTO T_UserLoginLog (UserId, LoginTime, LoginInIp, LoginType) VALUES (?,?,?,?)",
                       (user["Id"], now, request.remote_addr, "后台登陆"))
            db.commit()
            flash(f"欢迎回来, {user['Name']}!")
            return redirect(url_for("dashboard"))
        flash("账号或密码错误")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# --- Routes: Dashboard (数据大屏) ---

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    db = get_db()

    total_alarms = db.execute("SELECT COUNT(*) as c FROM T_DetectResult").fetchone()["c"]
    pending_alarms = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE Status='1'").fetchone()["c"]
    total_devices = db.execute("SELECT COUNT(*) as c FROM T_Device").fetchone()["c"]

    today_start = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")

    today_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime >= ?", (today_start,)).fetchone()["c"]
    week_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (week_ago,)).fetchone()["c"]
    month_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (month_ago,)).fetchone()["c"]
    year_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (year_ago,)).fetchone()["c"]

    recent_alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, a.Name as AreaName, u.Name as OperatorName FROM T_DetectResult dr LEFT JOIN T_Area a ON dr.AreaId=a.Id LEFT JOIN T_User u ON dr.OperateUserId=u.Id ORDER BY dr.CreatTime DESC LIMIT 30").fetchall()]

    earliest_row = db.execute("SELECT MIN(CreatTime) as m FROM T_DetectResult").fetchone()
    earliest_time = earliest_row["m"] if earliest_row and earliest_row["m"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    monthly_ranking = [dict(r) for r in db.execute(
        "SELECT COALESCE(a.Name,'?') as name, COUNT(*) as count FROM T_DetectResult dr LEFT JOIN T_Area a ON dr.AreaId=a.Id WHERE dr.CreatTime > ? GROUP BY a.Id ORDER BY count DESC LIMIT 5", (month_ago,)).fetchall()]
    max_rank = max([r["count"] for r in monthly_ranking]) if monthly_ranking else 1

    return render_template_string(DASHBOARD_TEMPLATE, user=user,
                                  total_alarms=total_alarms, pending_alarms=pending_alarms,
                                  total_devices=total_devices,
                                  today_count=today_count, week_count=week_count,
                                  month_count=month_count, year_count=year_count,
                                  recent_alarms=recent_alarms,
                                  monthly_ranking=monthly_ranking, max_rank=max_rank,
                                  earliest_time=earliest_time)


# --- Routes: System Config ---

@app.route("/admin/config", methods=["GET", "POST"])
@login_required
@admin_required
def system_config():
    db = get_db()
    if request.method == "POST":
        data = {k: request.form[k] for k in ["Name", "SiteName", "thresh", "width", "height", "video_times", "heartBeat", "exception_times"]}
        db.execute("UPDATE T_Site SET Name=?, SiteName=?, thresh=?, width=?, height=?, video_times=?, heartBeat=?, exception_times=? WHERE Id=1",
                   (data["Name"], data["SiteName"], float(data["thresh"]), float(data["width"]), float(data["height"]), float(data["video_times"]), float(data["heartBeat"]), float(data["exception_times"])))
        db.commit()
        add_log("系统配置", "修改", data)
        flash("系统配置已更新")
    site = db.execute("SELECT * FROM T_Site WHERE Id=1").fetchone()
    return render_template_string(CONFIG_TEMPLATE, user=get_current_user(), site=dict(site) if site else {})


# --- Routes: Department ---

@app.route("/admin/branch")
@login_required
@admin_required
def branch_list():
    db = get_db()
    branches = [dict(r) for r in db.execute("SELECT * FROM T_Branch ORDER BY Id").fetchall()]
    return render_template_string(BRANCH_TEMPLATE, user=get_current_user(), branches=branches)


@app.route("/admin/branch/add", methods=["POST"])
@login_required
@admin_required
def branch_add():
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO T_Branch (Name, ParentId, CreateTime, CreateBy, Remark) VALUES (?,?,?,?,?)",
               (request.form["Name"], int(request.form.get("ParentId", 0)), now, session["user_id"], request.form.get("Remark", "")))
    db.commit()
    add_log("部门管理", "增加", dict(request.form))
    flash("部门已添加")
    return redirect(url_for("branch_list"))


@app.route("/admin/branch/edit/<int:bid>", methods=["POST"])
@login_required
@admin_required
def branch_edit(bid):
    db = get_db()
    db.execute("UPDATE T_Branch SET Name=?, ParentId=?, Remark=? WHERE Id=?",
               (request.form["Name"], int(request.form.get("ParentId", 0)), request.form.get("Remark", ""), bid))
    db.commit()
    add_log("部门管理", "修改", dict(request.form))
    flash("部门已更新")
    return redirect(url_for("branch_list"))


@app.route("/admin/branch/delete/<int:bid>")
@login_required
@admin_required
def branch_delete(bid):
    db = get_db()
    db.execute("DELETE FROM T_Branch WHERE Id=?", (bid,))
    db.commit()
    add_log("部门管理", "删除", {"Id": bid})
    flash("部门已删除")
    return redirect(url_for("branch_list"))


# --- Routes: User ---

@app.route("/admin/user")
@login_required
@admin_required
def user_list():
    db = get_db()
    users = [dict(r) for r in db.execute(
        "SELECT u.*, b.Name as BranchName, a.Name as AreaName, r.Name as RoleName FROM T_User u LEFT JOIN T_Branch b ON u.BranchId=b.Id LEFT JOIN T_Area a ON u.AreaId=a.Id LEFT JOIN T_UserRole ur ON u.Id=ur.UserId LEFT JOIN T_Role r ON ur.RoleId=r.Id WHERE ur.IsDeleted='undeleted' ORDER BY u.Id").fetchall()]
    branches = [dict(r) for r in db.execute("SELECT * FROM T_Branch").fetchall()]
    areas = [dict(r) for r in db.execute("SELECT Id,Value as Name FROM T_Dictionary WHERE Key='AreaType'").fetchall()]
    roles = [dict(r) for r in db.execute("SELECT * FROM T_Role WHERE IsDelete=0").fetchall()]
    return render_template_string(USER_TEMPLATE, user=get_current_user(), users=users, branches=branches, areas=areas, roles=roles)


@app.route("/admin/user/add", methods=["POST"])
@login_required
@admin_required
def user_add():
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pwd = hash_pwd(request.form["Password"])
    db.execute("INSERT INTO T_User (Account, Name, AreaId, BranchId, Password, CreateTime, CreateBy) VALUES (?,?,?,?,?,?,?)",
               (request.form["Account"], request.form["Name"], int(request.form.get("AreaId", 1)), int(request.form.get("BranchId", 1)), pwd, now, session["user_id"]))
    uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute("INSERT INTO T_UserRole (UserId, RoleId, IsDefault, CreateTime, IsDeleted) VALUES (?,?,?,?,?)",
               (uid, int(request.form.get("RoleId", 2)), request.form.get("IsDefault", "isdefault"), now, "undeleted"))
    db.commit()
    add_log("用户管理", "增加", {k: v for k, v in request.form.items() if k != "Password"})
    flash("用户已添加")
    return redirect(url_for("user_list"))


@app.route("/admin/user/edit/<int:uid>", methods=["POST"])
@login_required
@admin_required
def user_edit(uid):
    db = get_db()
    pwd = request.form.get("Password", "")
    if pwd:
        db.execute("UPDATE T_User SET Account=?, Name=?, AreaId=?, BranchId=?, Password=?, Remark=? WHERE Id=?",
                   (request.form["Account"], request.form["Name"], int(request.form.get("AreaId", 1)), int(request.form.get("BranchId", 1)), hash_pwd(pwd), request.form.get("Remark", ""), uid))
    else:
        db.execute("UPDATE T_User SET Account=?, Name=?, AreaId=?, BranchId=?, Remark=? WHERE Id=?",
                   (request.form["Account"], request.form["Name"], int(request.form.get("AreaId", 1)), int(request.form.get("BranchId", 1)), request.form.get("Remark", ""), uid))
    if request.form.get("RoleId"):
        db.execute("UPDATE T_UserRole SET RoleId=? WHERE UserId=? AND IsDeleted='undeleted'",
                   (int(request.form["RoleId"]), uid))
    db.commit()
    add_log("用户管理", "修改", {k: v for k, v in request.form.items() if k != "Password"})
    flash("用户已更新")
    return redirect(url_for("user_list"))


@app.route("/admin/user/delete/<int:uid>")
@login_required
@admin_required
def user_delete(uid):
    db = get_db()
    db.execute("UPDATE T_UserRole SET IsDeleted='deleted' WHERE UserId=?", (uid,))
    db.commit()
    add_log("用户管理", "删除", {"Id": uid})
    flash("用户已删除")
    return redirect(url_for("user_list"))


# --- Routes: Role ---

@app.route("/admin/role")
@login_required
@admin_required
def role_list():
    db = get_db()
    roles = [dict(r) for r in db.execute("SELECT * FROM T_Role WHERE IsDelete=0").fetchall()]
    return render_template_string(ROLE_TEMPLATE, user=get_current_user(), roles=roles)


@app.route("/admin/role/add", methods=["POST"])
@login_required
@admin_required
def role_add():
    db = get_db()
    db.execute("INSERT INTO T_Role (Name, Description) VALUES (?,?)",
               (request.form["Name"], request.form.get("Description", "")))
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    authorities = request.form.getlist("authorities")
    for auth in authorities:
        db.execute("INSERT INTO T_Authority (RoleId, Authority) VALUES (?,?)", (rid, auth))
    db.commit()
    add_log("角色管理", "增加", dict(request.form))
    flash("角色已添加")
    return redirect(url_for("role_list"))


@app.route("/admin/role/edit/<int:rid>", methods=["POST"])
@login_required
@admin_required
def role_edit(rid):
    db = get_db()
    db.execute("UPDATE T_Role SET Name=?, Description=? WHERE Id=?",
               (request.form["Name"], request.form.get("Description", ""), rid))
    db.execute("DELETE FROM T_Authority WHERE RoleId=?", (rid,))
    authorities = request.form.getlist("authorities")
    for auth in authorities:
        db.execute("INSERT INTO T_Authority (RoleId, Authority) VALUES (?,?)", (rid, auth))
    db.commit()
    add_log("角色管理", "修改", dict(request.form))
    flash("角色已更新")
    return redirect(url_for("role_list"))


@app.route("/admin/role/delete/<int:rid>")
@login_required
@admin_required
def role_delete(rid):
    db = get_db()
    db.execute("UPDATE T_Role SET IsDelete=1 WHERE Id=?", (rid,))
    db.commit()
    add_log("角色管理", "删除", {"Id": rid})
    flash("角色已删除")
    return redirect(url_for("role_list"))


# --- Routes: Dictionary ---

@app.route("/admin/dictionary")
@login_required
@admin_required
def dictionary_list():
    db = get_db()
    keys = [dict(r) for r in db.execute("SELECT DISTINCT Key FROM T_Dictionary").fetchall()]
    items = [dict(r) for r in db.execute("SELECT * FROM T_Dictionary ORDER BY Key, Id").fetchall()]
    return render_template_string(DICT_TEMPLATE, user=get_current_user(), keys=keys, items=items)


@app.route("/admin/dictionary/add", methods=["POST"])
@login_required
@admin_required
def dictionary_add():
    db = get_db()
    db.execute("INSERT INTO T_Dictionary (Key, Value, Remark) VALUES (?,?,?)",
               (request.form["Key"], request.form["Value"], request.form.get("Remark", "")))
    db.commit()
    flash("字典项已添加")
    return redirect(url_for("dictionary_list"))


@app.route("/admin/dictionary/delete/<int:did>")
@login_required
@admin_required
def dictionary_delete(did):
    db = get_db()
    db.execute("DELETE FROM T_Dictionary WHERE Id=?", (did,))
    db.commit()
    flash("字典项已删除")
    return redirect(url_for("dictionary_list"))


# --- Routes: Device (AI分析盒) ---

@app.route("/admin/device")
@login_required
def device_list():
    db = get_db()
    devices = [dict(r) for r in db.execute(
        "SELECT d.*, a.Name as AreaName FROM T_Device d LEFT JOIN T_Area a ON d.AreaId=a.Id ORDER BY d.Id").fetchall()]
    areas = [dict(r) for r in db.execute("SELECT Id,Value as Name FROM T_Dictionary WHERE Key='AreaType'").fetchall()]
    return render_template_string(DEVICE_TEMPLATE, user=get_current_user(), devices=devices, areas=areas)


@app.route("/admin/device/add", methods=["POST"])
@login_required
@admin_required
def device_add():
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""INSERT INTO T_Device (MAC, Longitude, Latitude, Address, AreaId, ModelPerson, ModelInfo, Maintainer, CreateTime, StructuralInfo, DetailInfo, Remark)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
               (request.form.get("MAC", ""), request.form.get("Longitude", ""), request.form.get("Latitude", ""),
                request.form.get("Address", ""), int(request.form.get("AreaId", 1)), request.form.get("ModelPerson", ""),
                request.form.get("ModelInfo", ""), request.form.get("Maintainer", ""), now,
                request.form.get("StructuralInfo", ""), request.form.get("DetailInfo", ""), request.form.get("Remark", "")))
    db.commit()
    add_log("AI分析盒管理", "增加", dict(request.form))
    flash("AI分析盒已添加")
    return redirect(url_for("device_list"))


@app.route("/admin/device/edit/<int:did>", methods=["POST"])
@login_required
@admin_required
def device_edit(did):
    db = get_db()
    db.execute("""UPDATE T_Device SET MAC=?, Longitude=?, Latitude=?, Address=?, AreaId=?, ModelPerson=?, ModelInfo=?, Maintainer=?, StructuralInfo=?, DetailInfo=?, Remark=? WHERE Id=?""",
               (request.form.get("MAC", ""), request.form.get("Longitude", ""), request.form.get("Latitude", ""),
                request.form.get("Address", ""), int(request.form.get("AreaId", 1)), request.form.get("ModelPerson", ""),
                request.form.get("ModelInfo", ""), request.form.get("Maintainer", ""),
                request.form.get("StructuralInfo", ""), request.form.get("DetailInfo", ""), request.form.get("Remark", ""), did))
    db.commit()
    add_log("AI分析盒管理", "修改", dict(request.form))
    flash("AI分析盒已更新")
    return redirect(url_for("device_list"))


@app.route("/admin/device/delete/<int:did>")
@login_required
@admin_required
def device_delete(did):
    db = get_db()
    db.execute("DELETE FROM T_Device WHERE Id=?", (did,))
    db.commit()
    add_log("AI分析盒管理", "删除", {"Id": did})
    flash("AI分析盒已删除")
    return redirect(url_for("device_list"))


# --- Routes: Camera ---

@app.route("/admin/camera")
@login_required
def camera_list():
    db = get_db()
    cameras = [dict(r) for r in db.execute(
        "SELECT c.*, a.Name as AreaName, d.MAC as DeviceMAC, d.Address as DeviceAddress FROM T_Camera c LEFT JOIN T_Area a ON c.AreaId=a.Id LEFT JOIN T_Device d ON c.DeviceId=d.Id ORDER BY c.Id").fetchall()]
    areas = [dict(r) for r in db.execute("SELECT Id,Value as Name FROM T_Dictionary WHERE Key='AreaType'").fetchall()]
    devices = [dict(r) for r in db.execute("SELECT * FROM T_Device").fetchall()]
    return render_template_string(CAMERA_TEMPLATE, user=get_current_user(), cameras=cameras, areas=areas, devices=devices)


@app.route("/admin/camera/add", methods=["POST"])
@login_required
@admin_required
def camera_add():
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""INSERT INTO T_Camera (IP, MAC, CameraUrl, Name, Longitude, Latitude, AreaId, Type, InstallTime, BandWidth, Maintainer, DeviceId, Remark)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (request.form.get("IP", ""), request.form.get("MAC", ""), request.form.get("CameraUrl", ""),
                request.form.get("Name", ""), request.form.get("Longitude", ""), request.form.get("Latitude", ""),
                int(request.form.get("AreaId", 1)), request.form.get("Type", ""), now,
                float(request.form.get("BandWidth", 0)), request.form.get("Maintainer", ""),
                int(request.form.get("DeviceId", 1)), request.form.get("Remark", "")))
    db.commit()
    add_log("摄像头管理", "增加", dict(request.form))
    flash("摄像头已添加")
    return redirect(url_for("camera_list"))


@app.route("/admin/camera/edit/<int:cid>", methods=["POST"])
@login_required
@admin_required
def camera_edit(cid):
    db = get_db()
    db.execute("""UPDATE T_Camera SET IP=?, MAC=?, CameraUrl=?, Name=?, Longitude=?, Latitude=?, AreaId=?, Type=?, BandWidth=?, Maintainer=?, DeviceId=?, Remark=? WHERE Id=?""",
               (request.form.get("IP", ""), request.form.get("MAC", ""), request.form.get("CameraUrl", ""),
                request.form.get("Name", ""), request.form.get("Longitude", ""), request.form.get("Latitude", ""),
                int(request.form.get("AreaId", 1)), request.form.get("Type", ""),
                float(request.form.get("BandWidth", 0)), request.form.get("Maintainer", ""),
                int(request.form.get("DeviceId", 1)), request.form.get("Remark", ""), cid))
    db.commit()
    add_log("摄像头管理", "修改", dict(request.form))
    flash("摄像头已更新")
    return redirect(url_for("camera_list"))


@app.route("/admin/camera/delete/<int:cid>")
@login_required
@admin_required
def camera_delete(cid):
    db = get_db()
    db.execute("DELETE FROM T_Camera WHERE Id=?", (cid,))
    db.commit()
    add_log("摄像头管理", "删除", {"Id": cid})
    flash("摄像头已删除")
    return redirect(url_for("camera_list"))


# --- Routes: Alarm Events ---

@app.route("/admin/alarm")
@login_required
def alarm_list():
    db = get_db()
    alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, c.Name as CameraName, a.Name as AreaName, d.Address as DeviceAddress, u.Name as OperatorName FROM T_DetectResult dr LEFT JOIN T_Camera c ON dr.CameraId=c.Id LEFT JOIN T_Area a ON dr.AreaId=a.Id LEFT JOIN T_Device d ON dr.DeviceId=d.Id LEFT JOIN T_User u ON dr.OperateUserId=u.Id ORDER BY dr.CreatTime DESC").fetchall()]
    return render_template_string(ALARM_TEMPLATE, user=get_current_user(), alarms=alarms)


@app.route("/admin/alarm/process/<int:aid>", methods=["POST"])
@login_required
def alarm_process(aid):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE T_DetectResult SET Status='2', OperateUserId=?, OperateTime=?, UrgencyDegree=?, OperateResult=?, Description=? WHERE Id=?",
               (session["user_id"], now, request.form.get("UrgencyDegree", ""), request.form.get("OperateResult", ""), request.form.get("Description", ""), aid))
    db.commit()
    add_log("报警事件", "处理", {"alarm_id": aid, "result": request.form.get("OperateResult", "")})
    flash("事件已处理")
    ref = request.referrer
    if ref:
        if "/dashboard" in ref:
            return redirect(url_for("dashboard"))
        elif "/admin/audit" in ref:
            return redirect(url_for("audit_list"))
    return redirect(url_for("alarm_list"))


# --- Routes: Event Audit ---

@app.route("/admin/audit")
@login_required
def audit_list():
    db = get_db()
    user = get_current_user()
    # If the user is neither SuperAdmin nor Auditor, redirect to dashboard or show unauthorized
    if user["RoleName"] not in ["超级管理员", "审核人"]:
        flash("您没有审核权限")
        return redirect(url_for("dashboard"))
    
    alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, c.Name as CameraName, a.Name as AreaName, u.Name as OperatorName FROM T_DetectResult dr LEFT JOIN T_Camera c ON dr.CameraId=c.Id LEFT JOIN T_Area a ON dr.AreaId=a.Id LEFT JOIN T_User u ON dr.OperateUserId=u.Id WHERE dr.Status='2' ORDER BY dr.CreatTime DESC").fetchall()]
    return render_template_string(AUDIT_TEMPLATE, user=user, alarms=alarms)


@app.route("/admin/audit/approve/<int:aid>")
@login_required
def audit_approve(aid):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE T_DetectResult SET Status='3', AuditUserId=?, AuditTime=? WHERE Id=?",
               (session["user_id"], now, aid))
    db.commit()
    add_log("事件审核", "审核通过", {"alarm_id": aid})
    flash("审核已通过")
    ref = request.referrer
    if ref:
        if "/dashboard" in ref:
            return redirect(url_for("dashboard"))
        elif "/admin/alarm" in ref:
            return redirect(url_for("alarm_list"))
    return redirect(url_for("audit_list"))


@app.route("/admin/audit/reject/<int:aid>")
@login_required
def audit_reject(aid):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE T_DetectResult SET Status='1', AuditUserId=?, AuditTime=? WHERE Id=?",
               (session["user_id"], now, aid))
    db.commit()
    add_log("事件审核", "审核驳回", {"alarm_id": aid})
    flash("已驳回，需重新处理")
    ref = request.referrer
    if ref:
        if "/dashboard" in ref:
            return redirect(url_for("dashboard"))
        elif "/admin/alarm" in ref:
            return redirect(url_for("alarm_list"))
    return redirect(url_for("audit_list"))


# --- Routes: Camera Error ---

@app.route("/admin/camera_error")
@login_required
def camera_error_list():
    db = get_db()
    errors = [dict(r) for r in db.execute(
        "SELECT ce.*, c.Name as CameraName FROM T_CameraError ce LEFT JOIN T_Camera c ON ce.CameraId=c.Id ORDER BY ce.CreateTime DESC").fetchall()]
    return render_template_string(CAMERA_ERROR_TEMPLATE, user=get_current_user(), errors=errors)


# --- Routes: Device Error ---

@app.route("/admin/device_error")
@login_required
def device_error_list():
    db = get_db()
    errors = [dict(r) for r in db.execute(
        "SELECT de.*, d.Address as DeviceAddress, d.MAC as DeviceMAC FROM T_DeviceError de LEFT JOIN T_Device d ON de.DeviceId=d.Id ORDER BY de.CreateTime DESC").fetchall()]
    return render_template_string(DEVICE_ERROR_TEMPLATE, user=get_current_user(), errors=errors)


# --- Routes: Logs ---

@app.route("/admin/log/access")
@login_required
def access_log():
    db = get_db()
    logs = [dict(r) for r in db.execute(
        "SELECT l.*, u.Name as UserName FROM T_UserLoginLog l LEFT JOIN T_User u ON l.UserId=u.Id ORDER BY l.LoginTime DESC LIMIT 200").fetchall()]
    return render_template_string(ACCESS_LOG_TEMPLATE, user=get_current_user(), logs=logs)


@app.route("/admin/log/operate")
@login_required
def operate_log():
    db = get_db()
    logs = [dict(r) for r in db.execute(
        "SELECT l.*, u.Name as UserName FROM T_OperateLog l LEFT JOIN T_User u ON l.UserId=u.Id ORDER BY l.CreateTime DESC LIMIT 200").fetchall()]
    return render_template_string(OPERATE_LOG_TEMPLATE, user=get_current_user(), logs=logs)


# --- API: Edge Device Communication ---

@app.route("/api/device/heartbeat", methods=["POST"])
def api_heartbeat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "Invalid JSON"}), 400
        mac = data.get("device_mac", "")
        did = data.get("device_id", 1)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        device = db.execute("SELECT * FROM T_Device WHERE MAC=? OR Id=?", (mac, did)).fetchone()
        if device:
            db.execute("UPDATE T_Device SET LastConnectTime=?, AutoGenerateError='no' WHERE Id=?",
                       (now, device["Id"]))
        else:
            auto_err = "yes" if data.get("status") != "online" else "no"
            db.execute("""INSERT INTO T_Device (MAC, ModelInfo, LastConnectTime, AutoGenerateError)
                VALUES (?,?,?,?)""", (mac, data.get("model_info", "YOLOv11"), now, auto_err))
        db.commit()
        site = db.execute("SELECT * FROM T_Site WHERE Id=1").fetchone()
        config = {"thresh": site["thresh"], "width": site["width"], "height": site["height"],
                  "video_times": site["video_times"], "heartBeat": site["heartBeat"], "exception_times": site["exception_times"]} if site else {}
        return jsonify({"code": 200, "msg": "ok", "config": config})
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route("/api/alarm", methods=["POST"])
def api_alarm():
    try:
        db = get_db()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        picture_file = request.files.get("picture")
        video_file = request.files.get("video")
        picture_path = ""
        video_path = ""

        if picture_file:
            ext = os.path.splitext(picture_file.filename)[1] or ".jpg"
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}{ext}"
            filepath = UPLOAD_DIR / "pictures" / filename
            picture_file.save(str(filepath))
            picture_path = f"/uploads/pictures/{filename}"

        if video_file:
            ext = os.path.splitext(video_file.filename)[1] or ".mp4"
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}{ext}"
            filepath = UPLOAD_DIR / "videos" / filename
            video_file.save(str(filepath))
            video_path = f"/uploads/videos/{filename}"

        db.execute("""INSERT INTO T_DetectResult (Longitude, Latitude, Location, Picture, VideoUrl, AreaId, CreatTime, CameraId, DeviceId, Status)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (request.form.get("longitude", ""), request.form.get("latitude", ""),
                    request.form.get("location", ""), picture_path, video_path,
                    int(request.form.get("area_id", 1)), now,
                    int(request.form.get("camera_id", 1)), int(request.form.get("device_id", 1)), "1"))
        db.commit()
        aid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info(f"Alarm received: id={aid}")
        return jsonify({"code": 200, "msg": "ok", "alarm_id": aid})
    except Exception as e:
        logger.error(f"Alarm error: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route("/api/device/error", methods=["POST"])
def api_device_error():
    try:
        data = request.get_json()
        db = get_db()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("INSERT INTO T_DeviceError (DeviceId, MAC, CreateTime, ErrorCode, ErrorMsg) VALUES (?,?,?,?,?)",
                   (data.get("device_id", 1), data.get("device_mac", ""), now, data.get("error_code", ""), data.get("error_msg", "")))
        db.commit()
        return jsonify({"code": 200, "msg": "ok"})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@app.route("/api/stats")
@login_required
def api_stats():
    db = get_db()
    area = [dict(r) for r in db.execute(
        "SELECT a.Name as name, COUNT(dr.Id) as value FROM T_Area a LEFT JOIN T_DetectResult dr ON a.Id=dr.AreaId GROUP BY a.Id").fetchall()]
    time_data = [dict(r) for r in db.execute(
        "SELECT strftime('%Y-%m-%d', CreatTime) as date, COUNT(*) as count FROM T_DetectResult WHERE CreatTime > datetime('now','-30 day') GROUP BY date ORDER BY date").fetchall()]
    total = db.execute("SELECT COUNT(*) as c FROM T_DetectResult").fetchone()["c"]

    pending_alarms = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE Status='1'").fetchone()["c"]

    today_start = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")

    today_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime >= ?", (today_start,)).fetchone()["c"]
    week_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (week_ago,)).fetchone()["c"]
    month_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (month_ago,)).fetchone()["c"]
    year_count = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CreatTime > ?", (year_ago,)).fetchone()["c"]

    recent_alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, a.Name as AreaName, u.Name as OperatorName FROM T_DetectResult dr LEFT JOIN T_Area a ON dr.AreaId=a.Id LEFT JOIN T_User u ON dr.OperateUserId=u.Id ORDER BY dr.CreatTime DESC LIMIT 30").fetchall()]

    earliest_row = db.execute("SELECT MIN(CreatTime) as m FROM T_DetectResult").fetchone()
    earliest_time = earliest_row["m"] if earliest_row and earliest_row["m"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    monthly_ranking = [dict(r) for r in db.execute(
        "SELECT COALESCE(a.Name,'?') as name, COUNT(*) as count FROM T_DetectResult dr LEFT JOIN T_Area a ON dr.AreaId=a.Id WHERE dr.CreatTime > ? GROUP BY a.Id ORDER BY count DESC LIMIT 5", (month_ago,)).fetchall()]
    max_rank = max([r["count"] for r in monthly_ranking]) if monthly_ranking else 1

    return jsonify({
        "area_stats": area,
        "time_stats": time_data,
        "total": total,
        "today_count": today_count,
        "week_count": week_count,
        "month_count": month_count,
        "year_count": year_count,
        "pending_alarms": pending_alarms,
        "recent_alarms": recent_alarms,
        "monthly_ranking": monthly_ranking,
        "max_rank": max_rank,
        "earliest_time": earliest_time
    })


# --- Templates ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>视频AI智能识别及预警管理系统 - 登录</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
.glass-panel {
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
</head>
<body class="bg-gradient-to-tr from-[#030712] via-[#091124] to-[#030712] text-slate-100 min-h-screen flex items-center justify-center font-sans p-4">
<div class="glass-panel w-full max-w-md rounded-2xl p-8 shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex flex-col gap-6 relative overflow-hidden">
    <!-- Decorative glow -->
    <div class="absolute -right-10 -top-10 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl"></div>
    <div class="absolute -left-10 -bottom-10 w-32 h-32 bg-rose-500/10 rounded-full blur-2xl"></div>
    
    <div class="flex flex-col items-center gap-2 text-center">
        <div class="w-14 h-14 bg-gradient-to-br from-rose-500 to-orange-500 rounded-2xl flex items-center justify-center shadow-lg shadow-rose-950/40">
            <span class="text-3xl">🔥</span>
        </div>
        <h2 class="text-lg font-bold tracking-wider text-slate-100 mt-2">视频AI智能识别及预警管理</h2>
        <p class="text-xs text-slate-400">后台管理平台登录</p>
    </div>
    
    {% with msgs = get_flashed_messages() %}
    {% if msgs %}
    <div class="bg-rose-500/10 border border-rose-500/20 text-rose-450 px-4 py-2.5 rounded-lg text-xs font-semibold animate-pulse">
        {{ msgs[0] }}
    </div>
    {% endif %}
    {% endwith %}
    
    <form method="post" class="flex flex-col gap-4 text-xs">
        <div class="flex flex-col gap-1.5">
            <label class="text-slate-400 font-medium">账号</label>
            <input type="text" name="account" placeholder="请输入您的账号" required autofocus class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3.5 py-2.5 text-slate-200 placeholder-slate-650 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
            <label class="text-slate-400 font-medium">密码</label>
            <input type="password" name="password" placeholder="请输入您的密码" required class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3.5 py-2.5 text-slate-200 placeholder-slate-650 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <button type="submit" class="w-full bg-gradient-to-r from-rose-600 to-orange-600 hover:from-rose-500 hover:to-orange-500 text-white font-bold py-3 rounded-lg mt-2 transition duration-300 active:scale-95 shadow-lg shadow-rose-950/30">登 录</button>
    </form>
    
    <div class="border-t border-slate-800/80 pt-4 flex flex-col gap-1 text-center text-[10px] text-slate-500">
        <p>测试账号: 管理员 (admin/123456) | 处理人 (chuli001/123456)</p>
        <p class="font-mono mt-0.5">&copy; 2026 Fire AI Detection System. All rights reserved.</p>
    </div>
</div>
</body>
</html>
"""

BASE_NAV = """
<header class="flex justify-between items-center h-14 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-md px-6 z-[1000] w-full fixed top-0 left-0 right-0 text-slate-100 font-sans">
  <div class="flex items-center gap-3">
    <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#22d3ee] animate-pulse"></span>
    <h1 class="m-0 font-bold text-sm tracking-wider bg-gradient-to-r from-slate-100 to-slate-300 bg-clip-text text-transparent">
      视频 AI 智能识别及预警平台
    </h1>
  </div>
  <nav class="flex items-center gap-4 text-xs">
    <a href="/dashboard" id="nav-dashboard" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-205 hover:text-slate-100 hover:bg-slate-900/50 text-slate-400 border border-transparent">
      数据大屏
    </a>
    {% if user.RoleName == '超级管理员' %}
    <a href="/admin/device" id="nav-device" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-205 hover:text-slate-100 hover:bg-slate-900/50 text-slate-400 border border-transparent">
      资源管理
    </a>
    <a href="/admin/config" id="nav-config" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-205 hover:text-slate-100 hover:bg-slate-900/50 text-slate-400 border border-transparent">
      系统设置
    </a>
    {% endif %}
    <a href="/admin/alarm" id="nav-alarm" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-205 hover:text-slate-100 hover:bg-slate-900/50 text-slate-400 border border-transparent">
      预警中心
    </a>
  </nav>
  <div class="flex items-center gap-4 text-xs">
    <span id="nav-clock" class="text-cyan-300 font-mono font-bold tracking-wider mr-2 hidden md:inline-block drop-shadow-[0_0_4px_rgba(34,211,238,0.25)]"></span>
    <span class="inline-flex items-center gap-1.5 text-emerald-450 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 rounded-full font-semibold text-[10px]">
      <span class="w-1.5 h-1.5 rounded-full bg-emerald-450"></span> 在线
    </span>
    <span class="text-slate-300 font-medium">{{ user.Name }}</span>
    <a href="/logout" class="text-rose-500 hover:text-rose-455 transition-colors font-semibold">退出</a>
  </div>
</header>
<div class="h-14"></div>
<script>
document.addEventListener("DOMContentLoaded", function() {
  // Navigation Clock Update
  function updateNavClock() {
    const el = document.getElementById("nav-clock");
    if (el) {
      const now = new Date();
      el.textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
    }
  }
  updateNavClock();
  setInterval(updateNavClock, 1000);

  const path = window.location.pathname;
  let activeId = "";
  if (path.includes("/dashboard")) activeId = "nav-dashboard";
  else if (path.includes("/admin/device") || path.includes("/admin/camera")) activeId = "nav-device";
  else if (path.includes("/admin/config") || path.includes("/admin/branch") || path.includes("/admin/user") || path.includes("/admin/role") || path.includes("/admin/dictionary")) activeId = "nav-config";
  else if (path.includes("/admin/alarm") || path.includes("/admin/audit") || path.includes("/admin/camera_error") || path.includes("/admin/device_error") || path.includes("/admin/log")) activeId = "nav-alarm";
  
  if (activeId) {
    const activeEl = document.getElementById(activeId);
    if (activeEl) {
      activeEl.classList.remove("text-slate-400");
      activeEl.classList.add("text-cyan-400", "bg-cyan-500/10", "border-cyan-500/20");
    }
  }
});
</script>
"""

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>视频 AI 智能识别及预警平台</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    .tech-grid-diagonal {
      background-image: 
        linear-gradient(rgba(34, 211, 238, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(34, 211, 238, 0.06) 1px, transparent 1px),
        repeating-linear-gradient(45deg, rgba(244, 63, 94, 0.02) 0px, rgba(244, 63, 94, 0.02) 10px, transparent 10px, transparent 20px);
      background-size: 20px 20px, 20px 20px, 15px 15px;
    }
    .scrollbar-thin::-webkit-scrollbar { width: 4px; height: 4px; }
    .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
    .scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
    .glass-panel {
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.06);
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes scaleIn {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }
    .animate-fade-in {
      animation: fadeIn 0.2s ease-out forwards;
    }
    .animate-scale-in {
      animation: scaleIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }
  </style>
</head>
<body class="bg-gradient-to-tr from-[#030712] via-[#091124] to-[#030712] text-slate-100 h-screen w-screen overflow-hidden flex flex-col font-sans">
""" + BASE_NAV + """
<main class="flex-1 grid grid-cols-12 gap-5 p-5 h-[calc(100vh-56px)] overflow-hidden">
<!-- Left Column: Search & Alarms Timeline -->
<section class="col-span-3 flex flex-col gap-5 h-full overflow-hidden">
  <!-- Search Panel -->
  <div class="glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-3">
    <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
      <span class="w-1.5 h-3.5 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee]"></span>
      条件查询
    </h2>
    <div class="flex flex-col gap-2.5 text-[11px]">
      <div class="flex flex-col gap-1">
        <label class="text-slate-400 font-medium">地址查询</label>
        <input type="text" id="searchLocation" placeholder="输入地址搜索..." class="w-full bg-slate-950/50 border border-slate-800/80 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-650 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-slate-400 font-medium">开始时间</label>
        <input type="datetime-local" id="startTime" class="w-full bg-slate-950/50 border border-slate-800/80 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-slate-400 font-medium">结束时间</label>
        <input type="datetime-local" id="endTime" class="w-full bg-slate-950/50 border border-slate-800/80 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex gap-2 mt-1">
        <button onclick="handleSearch()" class="flex-1 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 py-2 rounded-lg font-semibold transition active:scale-95">查询</button>
        <button onclick="resetSearch()" class="flex-1 bg-slate-800/50 hover:bg-slate-800 border border-slate-700 text-slate-300 py-2 rounded-lg font-semibold transition active:scale-95">重置</button>
      </div>
    </div>
  </div>
  
  <!-- Alarm Timeline -->
  <div class="flex-1 glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-3 overflow-hidden">
    <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="w-1.5 h-3.5 bg-rose-500 rounded-full shadow-[0_0_8px_#f43f5e]"></span>
        报警记录
      </div>
      <span class="text-rose-400 text-[10px] font-bold bg-rose-500/10 border border-rose-500/20 px-2.5 py-0.5 rounded-full" id="pendingAlarmsCount">{{ pending_alarms }}</span>
    </h2>
    <div class="flex-1 overflow-y-auto pr-1 flex flex-col gap-2 text-xs scrollbar-thin" id="timelineContainer">
      <div class="relative border-l border-slate-800 ml-2 pl-4 flex flex-col gap-3 py-2" id="timelineList">
        {% for a in recent_alarms %}
        <div class="relative mb-2">
          <span class="absolute -left-[21px] mt-1 w-2.5 h-2.5 rounded-full border border-rose-500 bg-slate-950 shadow-[0_0_6px_#f43f5e] flex items-center justify-center">
            <span class="w-1 h-1 rounded-full bg-rose-500 animate-pulse"></span>
          </span>
          <div class="bg-slate-950/25 border border-slate-800 rounded-xl p-3 flex flex-col gap-1 transition duration-200 cursor-pointer hover:border-cyan-500/40 hover:bg-slate-950/40" onclick="showAlarmDetail({{ a.Id }})">
            <div class="flex justify-between items-center">
              <span class="text-rose-400 font-semibold text-[10px]">火焰预警</span>
              <span class="text-slate-500 text-[9px] font-mono">{{ a.CreatTime or '--' }}</span>
            </div>
            <span class="text-slate-300 text-xs truncate">{{ a.Location or a.AreaName or '未知位置' }}</span>
          </div>
        </div>
        {% else %}
        <div class="flex items-center justify-center h-full text-slate-600 text-xs py-8">暂无报警记录</div>
        {% endfor %}
      </div>
    </div>
  </div>
</section>

<!-- Middle Column: Monitoring & Snapshots / Charts -->
<section class="col-span-6 flex flex-col gap-5 h-full overflow-hidden">
  <!-- Realtime Stream -->
  <div class="flex-1 glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-3 overflow-hidden">
    <div class="flex items-center justify-between">
      <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
        <span class="w-1.5 h-3.5 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee]"></span>
        实时监控画面
      </h2>
      <span class="text-[9px] text-slate-400 bg-slate-950/50 px-3 py-0.5 rounded-full border border-slate-800">1280x720 | WebSocket</span>
    </div>
    <div class="flex-1 bg-slate-950/60 rounded-xl relative overflow-hidden flex items-center justify-center tech-grid-diagonal border border-slate-900 shadow-inner">
      <img id="cameraFrame" class="hidden absolute inset-0 w-full h-full object-contain">
      <div id="videoOffline" class="flex flex-col items-center gap-2.5 z-10 text-center">
        <svg class="w-12 h-12 text-slate-600 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
        </svg>
        <span class="text-slate-400 text-xs font-semibold tracking-wider">视频流未连接 (Camera Offline)</span>
      </div>
      <span id="videoTag" class="hidden absolute top-3 left-3 bg-rose-500/10 border border-rose-500/20 text-rose-450 text-[9px] font-bold px-2.5 py-0.5 rounded uppercase tracking-wider shadow-md">Offline</span>
    </div>
  </div>
  
  <!-- Bottom Section: Snapshots & Trend Chart -->
  <div class="h-52 flex gap-5 shrink-0 overflow-hidden">
    <!-- Snapshots -->
    <div class="w-1/2 glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-2.5 overflow-hidden border border-slate-800/80">
      <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
        <span class="w-1.5 h-3.5 bg-orange-500 rounded-full shadow-[0_0_8px_#f97316]"></span>
        疑似火灾抓拍记录
      </h2>
      <div class="flex-1 flex gap-3 overflow-x-auto pb-1 scrollbar-thin" id="snapshotsContainer">
        {% set snapshots = recent_alarms|selectattr('Picture')|list %}
        {% for a in snapshots[:4] %}
        <div class="w-40 shrink-0 rounded-xl bg-slate-950/40 border border-rose-500/35 p-1.5 flex flex-col gap-1 shadow-[0_0_10px_rgba(244,63,94,0.12)] hover:border-rose-500 hover:shadow-[0_0_15px_rgba(244,63,94,0.25)] transition duration-300 cursor-pointer" onclick="showAlarmDetail({{ a.Id }})">
          <div class="relative aspect-video rounded-lg overflow-hidden border border-rose-500/20">
            <img src="{{ a.Picture }}" class="w-full h-full object-cover">
            <span class="absolute bottom-1 right-1 bg-rose-600/90 text-white text-[8px] font-bold px-1.5 py-0.5 rounded shadow shadow-rose-950/50 tracking-wider">疑似火灾</span>
          </div>
          <div class="flex flex-col gap-0.5 px-0.5">
            <div class="flex justify-between items-center text-[9px]">
              <span class="text-orange-400 font-mono font-semibold">{{ a.CreatTime[11:19] if a.CreatTime else '--' }}</span>
              <span class="text-slate-400 truncate max-w-[70px] font-medium">{{ a.Location or '--' }}</span>
            </div>
          </div>
        </div>
        {% else %}
        <div class="flex items-center justify-center w-full text-slate-650 text-xs">暂无抓拍记录</div>
        {% endfor %}
      </div>
    </div>
    
    <!-- Trend Chart -->
    <div class="w-1/2 glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-2 overflow-hidden border border-slate-800/80">
      <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
        <span class="w-1.5 h-3.5 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee]"></span>
        30天内预警趋势
      </h2>
      <div id="trendChart" class="flex-1 w-full h-full"></div>
    </div>
  </div>
</section>

<!-- Right Column: Time, Statistics & Ranking / Area Distribution -->
<section class="col-span-3 flex flex-col gap-5 h-full overflow-hidden">
  <!-- Clock & Date -->
  <div class="glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-2 items-center text-center relative overflow-hidden shrink-0">
    <div class="absolute -right-4 -top-4 w-16 h-16 bg-cyan-500/10 rounded-full blur-xl"></div>
    <div id="clock" class="text-3xl font-black tracking-widest text-cyan-300 font-mono drop-shadow-[0_0_8px_rgba(34,211,238,0.4)]">--</div>
    <div class="text-[10px] text-slate-400 font-bold tracking-wider uppercase" id="liveDate">--</div>
  </div>
  
  <!-- Stats Box -->
  <div class="glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-3 shrink-0">
    <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
      <span class="w-1.5 h-3.5 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee]"></span>
      预警数据统计
    </h2>
    <div class="grid grid-cols-2 gap-3 text-center">
      <div class="bg-slate-950/50 border border-slate-850 rounded-xl p-3 flex flex-col gap-1 relative overflow-hidden group hover:border-cyan-500/40 hover:shadow-[0_0_15px_rgba(6,182,212,0.25)] transition duration-300">
        <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center justify-center gap-1">⏰ 今日预警</span>
        <span class="text-2xl font-black text-cyan-400 font-mono drop-shadow-[0_0_8px_rgba(34,211,238,0.5)]" id="statToday">{{ today_count }}</span>
        <div class="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
      </div>
      <div class="bg-slate-950/50 border border-slate-850 rounded-xl p-3 flex flex-col gap-1 relative overflow-hidden group hover:border-orange-500/40 hover:shadow-[0_0_15px_rgba(249,115,22,0.25)] transition duration-300">
        <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center justify-center gap-1">📅 本周预警</span>
        <span class="text-2xl font-black text-orange-400 font-mono drop-shadow-[0_0_8px_rgba(249,115,22,0.5)]" id="statWeek">{{ week_count }}</span>
        <div class="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-orange-500 to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
      </div>
      <div class="bg-slate-950/50 border border-slate-850 rounded-xl p-3 flex flex-col gap-1 relative overflow-hidden group hover:border-pink-500/40 hover:shadow-[0_0_15px_rgba(244,63,94,0.25)] transition duration-300">
        <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center justify-center gap-1">📊 本月预警</span>
        <span class="text-2xl font-black text-pink-400 font-mono drop-shadow-[0_0_8px_rgba(244,63,94,0.5)]" id="statMonth">{{ month_count }}</span>
        <div class="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-pink-500 to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
      </div>
      <div class="bg-slate-950/50 border border-slate-850 rounded-xl p-3 flex flex-col gap-1 relative overflow-hidden group hover:border-emerald-500/40 hover:shadow-[0_0_15px_rgba(16,185,129,0.25)] transition duration-300">
        <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center justify-center gap-1">✨ 本年预警</span>
        <span class="text-2xl font-black text-emerald-400 font-mono drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]" id="statYear">{{ year_count }}</span>
        <div class="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-500 to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
      </div>
      <div class="bg-slate-950/50 border border-slate-850 rounded-xl p-3 flex flex-col gap-1 relative overflow-hidden group hover:border-blue-500/40 hover:shadow-[0_0_15px_rgba(59,130,246,0.25)] transition duration-300 col-span-2">
        <div class="flex justify-between items-center px-2">
          <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center gap-1">📈 累计预警</span>
          <span class="text-slate-400 text-[10px] font-semibold tracking-wider flex items-center gap-1">🚨 待处理预警</span>
        </div>
        <div class="flex justify-between items-center px-4 mt-0.5">
          <span class="text-2xl font-black text-blue-400 font-mono drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]" id="statTotal">{{ total_alarms }}</span>
          <span class="text-2xl font-black text-rose-500 font-mono drop-shadow-[0_0_8px_rgba(244,63,94,0.5)] animate-pulse" id="statPending">{{ pending_alarms }}</span>
        </div>
        <div class="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-blue-500 to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
      </div>
    </div>
  </div>
  
  <!-- Ranking List -->
  <div class="flex-1 glass-panel rounded-2xl p-4 shadow-[0_8px_32px_rgba(0,0,0,0.37)] flex flex-col gap-3 overflow-hidden border border-slate-800/80">
    <div class="flex items-center justify-between">
      <h2 class="text-xs font-bold tracking-wider text-slate-200 flex items-center gap-2">
        <span class="w-1.5 h-3.5 bg-amber-500 rounded-full shadow-[0_0_8px_#f59e0b]"></span>
        地区预警排行榜
      </h2>
    </div>
    
    <div class="flex-1 overflow-y-auto scrollbar-thin pr-1">
      <div class="flex flex-col gap-3.5 justify-center py-1" id="rankingList">
        {% for item in monthly_ranking %}
        <div class="flex flex-col gap-1.5">
          <div class="flex justify-between text-[11px] font-medium">
            <span class="text-slate-300">{{ item.name }}</span>
            <span class="text-amber-400 font-semibold">{{ item.count }} 次</span>
          </div>
          <div class="h-2 w-full bg-slate-950/60 rounded-full overflow-hidden border border-slate-800/40">
            <div class="h-full bg-gradient-to-r from-cyan-400 to-blue-500 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.3)]" style="width:{{ (item.count/max_rank*100)|round|int }}%"></div>
          </div>
        </div>
        {% else %}
        <div class="flex items-center justify-center h-full text-slate-655 text-xs">暂无数据</div>
        {% endfor %}
      </div>
    </div>
  </div>
</section>
</main>

<script>
// Digital Clock & Date Update
function upd(){
  var n=new Date();
  document.getElementById('clock').textContent=n.toLocaleTimeString('zh-CN',{hour12:false});
  document.getElementById('liveDate').textContent=n.getFullYear()+'年'+(n.getMonth()+1).toString().padStart(2,'0')+'月'+n.getDate().toString().padStart(2,'0')+'日 星期'+['日','一','二','三','四','五','六'][n.getDay()];
}
upd();
setInterval(upd,1000);

// WebSocket connection for live camera stream
var ws=null,wsReconnectTimer=null,wsReconnectDelay=1000;
function wsConnect(){
  if(ws){try{ws.close();}catch(e){}}
  
  // Try to use current hostname first
  const host = location.hostname || '127.0.0.1';
  const wsUrl = 'ws://' + host + ':9999';
  
  console.log('[WS] Connecting to: ' + wsUrl);
  ws=new WebSocket(wsUrl);
  ws.binaryType='blob';
  
  ws.onopen=function(){
    console.log('[WS] Connected to ' + wsUrl);
    document.getElementById('videoOffline').style.display='none';
    document.getElementById('cameraFrame').classList.remove('hidden');
    var t=document.getElementById('videoTag');
    t.classList.remove('hidden');
    t.textContent='Live';
    t.className='absolute top-3 left-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-450 text-[9px] font-bold px-2.5 py-0.5 rounded uppercase tracking-wider shadow-md';
    wsReconnectDelay=1000;
  };
  
  ws.onmessage=function(e){
    var u=URL.createObjectURL(e.data);
    var img=document.getElementById('cameraFrame');
    img.onload=function(){URL.revokeObjectURL(u);};
    img.src=u;
  };
  
  ws.onclose=function(e){
    console.log('[WS] Closed. Code:', e.code);
    document.getElementById('videoOffline').style.display='flex';
    document.getElementById('cameraFrame').classList.add('hidden');
    var t=document.getElementById('videoTag');
    t.classList.remove('hidden');
    t.textContent='Offline';
    t.className='absolute top-3 left-3 bg-rose-500/10 border border-rose-500/20 text-rose-450 text-[9px] font-bold px-2.5 py-0.5 rounded uppercase tracking-wider shadow-md';
    
    wsReconnectTimer=setTimeout(wsConnect, wsReconnectDelay);
    wsReconnectDelay=Math.min(wsReconnectDelay*2, 10000);
  };
  
  ws.onerror=function(e){
    console.error('[WS] Error observed:', e);
  };
}
wsConnect();

// Search / Query functionality
var filterLocation = '';
var filterStart = '';
var filterEnd = '';

var earliestAlarmTime = "{{ earliest_time }}";
function formatDateTimeLocal(dateStr) {
  if (!dateStr) return "";
  return dateStr.replace(' ', 'T').substring(0, 16);
}
function getNowDateTimeLocal() {
  const now = new Date();
  const tzOffset = now.getTimezoneOffset() * 60000;
  return (new Date(now - tzOffset)).toISOString().slice(0, 16);
}

// Set initial datetime picker values on load
document.addEventListener("DOMContentLoaded", function() {
  const startInput = document.getElementById('startTime');
  const endInput = document.getElementById('endTime');
  if (startInput) startInput.value = formatDateTimeLocal(earliestAlarmTime);
  if (endInput) endInput.value = getNowDateTimeLocal();
});

function handleSearch() {
  filterLocation = document.getElementById('searchLocation').value.trim().toLowerCase();
  filterStart = document.getElementById('startTime').value;
  filterEnd = document.getElementById('endTime').value;
  fetchRealtimeData();
}

function resetSearch() {
  document.getElementById('searchLocation').value = '';
  const startInput = document.getElementById('startTime');
  const endInput = document.getElementById('endTime');
  if (startInput) startInput.value = formatDateTimeLocal(earliestAlarmTime);
  if (endInput) endInput.value = getNowDateTimeLocal();
  filterLocation = '';
  filterStart = '';
  filterEnd = '';
  fetchRealtimeData();
}

var trendChartInstance = null;
var pieChartInstance = null;

// ECharts Themes & Configurations
const chartTextColor = '#94a3b8';
const chartLineColor = 'rgba(51, 65, 85, 0.3)';

const trendOption = {
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15, 23, 42, 0.9)',
    borderColor: 'rgba(34, 211, 238, 0.3)',
    textStyle: { color: '#f1f5f9', fontSize: 10 },
    borderWidth: 1,
    borderRadius: 8,
    shadowColor: 'rgba(0, 0, 0, 0.5)',
    shadowBlur: 10
  },
  grid: {
    top: '12%',
    left: '2%',
    right: '2%',
    bottom: '2%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: [],
    axisLine: { lineStyle: { color: chartLineColor } },
    axisLabel: { color: chartTextColor, fontSize: 8 },
    splitLine: { show: false }
  },
  yAxis: {
    type: 'value',
    axisLine: { show: false },
    axisLabel: { color: chartTextColor, fontSize: 8 },
    splitLine: { lineStyle: { color: chartLineColor, type: 'dashed' } }
  },
  series: [{
    name: '报警次数',
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    showSymbol: false,
    itemStyle: { color: '#22d3ee' },
    lineStyle: { width: 3, color: '#22d3ee', shadowColor: 'rgba(34, 211, 238, 0.5)', shadowBlur: 8 },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(34, 211, 238, 0.25)' },
        { offset: 1, color: 'rgba(34, 211, 238, 0)' }
      ])
    },
    data: []
  }]
};

// Global alarmData mapping for details modal
const alarmData = {
  {% for a in recent_alarms %}
  "{{ a.Id }}": {
    id: {{ a.Id }},
    time: "{{ a.CreatTime or '' }}",
    location: "{{ (a.Location or a.CameraName or '未知位置')|replace('\\\\', '\\\\\\\\')|replace('"', '\\"') }}",
    picture: "{{ a.Picture or '' }}",
    videoUrl: "{{ a.VideoUrl or '' }}",
    status: "{{ a.Status }}",
    desc: "{{ (a.Description or '')|replace('\\\\', '\\\\\\\\')|replace('"', '\\"')|replace('\r', '')|replace('\n', '\\n') }}",
    urgency: "{{ a.UrgencyDegree or '' }}",
    result: "{{ a.OperateResult or '' }}",
    operator: "{{ a.OperatorName or '' }}",
    operateTime: "{{ a.OperateTime or '' }}"
  },
  {% endfor %}
};

function showAlarmDetail(id) {
  const a = alarmData[id];
  if (!a) return;

  const form = document.getElementById('modalProcessForm');
  if (form) form.action = '/admin/alarm/process/' + id;
  
  const timeEl = document.getElementById('modalAlarmTime');
  if (timeEl) timeEl.textContent = a.time || '--';
  
  const locEl = document.getElementById('modalAlarmLocation');
  if (locEl) locEl.textContent = a.location || '未知位置';
  
  // Picture
  const img = document.getElementById('modalAlarmImage');
  const noImg = document.getElementById('modalAlarmNoImage');
  if (img && noImg) {
    if (a.picture) {
      img.src = a.picture;
      img.classList.remove('hidden');
      noImg.classList.add('hidden');
    } else {
      img.src = '';
      img.classList.add('hidden');
      noImg.classList.remove('hidden');
    }
  }
  
  // Video
  const video = document.getElementById('modalAlarmVideo');
  const noVideo = document.getElementById('modalAlarmNoVideo');
  if (video && noVideo) {
    if (a.videoUrl) {
      video.src = a.videoUrl;
      video.classList.remove('hidden');
      noVideo.classList.add('hidden');
    } else {
      video.src = '';
      video.classList.add('hidden');
      noVideo.classList.remove('hidden');
    }
  }

  const statusEl = document.getElementById('modalAlarmStatus');
  if (statusEl) {
    if (a.status === '1') {
      statusEl.textContent = '报警 (未处理)';
      statusEl.className = 'text-rose-400 font-bold';
      const pForm = document.getElementById('modalProcessForm');
      if (pForm) pForm.classList.remove('hidden');
      const pInfo = document.getElementById('modalProcessedInfo');
      if (pInfo) pInfo.classList.add('hidden');
    } else {
      const statusText = a.status === '2' ? '待审核' : '已审核';
      statusEl.textContent = statusText;
      statusEl.className = a.status === '2' ? 'text-amber-450 font-bold' : 'text-emerald-450 font-bold';
      
      const pForm = document.getElementById('modalProcessForm');
      if (pForm) pForm.classList.add('hidden');
      const pInfo = document.getElementById('modalProcessedInfo');
      if (pInfo) pInfo.classList.remove('hidden');
      
      const opEl = document.getElementById('modalInfoOperator');
      if (opEl) opEl.textContent = a.operator || '系统/未知';
      const opTimeEl = document.getElementById('modalInfoTime');
      if (opTimeEl) opTimeEl.textContent = a.operateTime || '--';
      const opResEl = document.getElementById('modalInfoResult');
      if (opResEl) opResEl.textContent = a.result || '--';
      const opUrgEl = document.getElementById('modalInfoUrgency');
      if (opUrgEl) opUrgEl.textContent = a.urgency || '普通';
      const opDescEl = document.getElementById('modalInfoDesc');
      if (opDescEl) opDescEl.textContent = a.desc || '无备注';
      
      const auditActions = document.getElementById('modalAuditActions');
      if (auditActions) {
        if (a.status === '2') {
          auditActions.classList.remove('hidden');
          const appBtn = document.getElementById('modalAuditApproveBtn');
          if (appBtn) appBtn.href = '/admin/audit/approve/' + id;
          const rejBtn = document.getElementById('modalAuditRejectBtn');
          if (rejBtn) rejBtn.href = '/admin/audit/reject/' + id;
        } else {
          auditActions.classList.add('hidden');
        }
      }
    }
  }

  const modal = document.getElementById('detailModal');
  if (modal) modal.classList.remove('hidden');
}

function closeAlarmDetail() {
  const modal = document.getElementById('detailModal');
  if (modal) modal.classList.add('hidden');
  const video = document.getElementById('modalAlarmVideo');
  if (video) {
    video.pause();
  }
}

// 2s Polling for Real-Time Console Data
function fetchRealtimeData() {
  fetch('/api/stats')
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.json();
    })
    .then(data => {
      // Update stats count indicators
      document.getElementById('statToday').textContent = data.today_count;
      document.getElementById('statWeek').textContent = data.week_count;
      document.getElementById('statMonth').textContent = data.month_count;
      document.getElementById('statYear').textContent = data.year_count;
      
      const statTotal = document.getElementById('statTotal');
      if (statTotal) statTotal.textContent = data.total;
      
      const statPending = document.getElementById('statPending');
      if (statPending) statPending.textContent = data.pending_alarms;
      
      const pendingBadge = document.getElementById('pendingAlarmsCount');
      if (pendingBadge) pendingBadge.textContent = data.pending_alarms;

      // Update global alarmData mapping dynamically
      (data.recent_alarms || []).forEach(a => {
        alarmData[a.Id] = {
          id: a.Id,
          time: a.CreatTime || '',
          location: a.Location || a.AreaName || '未知位置',
          picture: a.Picture || '',
          videoUrl: a.VideoUrl || '',
          status: a.Status,
          desc: a.Description || '',
          urgency: a.UrgencyDegree || '',
          result: a.OperateResult || '',
          operator: a.OperatorName || '',
          operateTime: a.OperateTime || ''
        };
      });

      // Filter recent alarms locally based on query conditions
      let filteredAlarms = data.recent_alarms || [];
      if (filterLocation) {
        filteredAlarms = filteredAlarms.filter(a => {
          const loc = (a.Location || a.AreaName || '').toLowerCase();
          return loc.includes(filterLocation);
        });
      }
      if (filterStart) {
        const startMs = new Date(filterStart).getTime();
        filteredAlarms = filteredAlarms.filter(a => {
          if (!a.CreatTime) return false;
          const alarmMs = new Date(a.CreatTime.replace(' ', 'T')).getTime();
          return alarmMs >= startMs;
        });
      }
      if (filterEnd) {
        const endMs = new Date(filterEnd).getTime();
        filteredAlarms = filteredAlarms.filter(a => {
          if (!a.CreatTime) return false;
          const alarmMs = new Date(a.CreatTime.replace(' ', 'T')).getTime();
          return alarmMs <= endMs;
        });
      }

      // Update Left Timeline (recent_alarms)
      const timelineList = document.getElementById('timelineList');
      if (timelineList) {
        if (filteredAlarms.length === 0) {
          timelineList.innerHTML = '<div class="text-slate-655 text-center py-8">暂无报警记录</div>';
        } else {
          let timelineHtml = '';
          filteredAlarms.forEach(a => {
            const location = a.Location || a.AreaName || '未知位置';
            const timeStr = a.CreatTime || '--';
            
            timelineHtml += `
            <div class="relative mb-2">
              <span class="absolute -left-[21px] mt-1 w-2.5 h-2.5 rounded-full border border-rose-500 bg-slate-950 shadow-[0_0_6px_#f43f5e] flex items-center justify-center">
                <span class="w-1 h-1 rounded-full bg-rose-500 animate-pulse"></span>
              </span>
              <div class="bg-slate-950/25 border border-slate-800 rounded-xl p-3 flex flex-col gap-1 transition duration-200 cursor-pointer hover:border-cyan-500/40 hover:bg-slate-950/40" onclick="showAlarmDetail(${a.Id})">
                <div class="flex justify-between items-center">
                  <span class="text-rose-400 font-semibold text-[10px]">火焰预警</span>
                  <span class="text-slate-500 text-[9px] font-mono">${timeStr}</span>
                </div>
                <span class="text-slate-300 text-xs truncate">${location}</span>
              </div>
            </div>`;
          });
          timelineList.innerHTML = timelineHtml;
        }
      }

      // Update Middle Snapshots (recent_alarms with Picture)
      const snapshotsContainer = document.getElementById('snapshotsContainer');
      if (snapshotsContainer) {
        const snapshots = (data.recent_alarms || []).filter(a => a.Picture);
        if (snapshots.length === 0) {
          snapshotsContainer.innerHTML = '<div class="flex items-center justify-center w-full text-slate-655 text-xs py-8">暂无抓拍记录</div>';
        } else {
          let snapshotsHtml = '';
          snapshots.slice(0, 4).forEach(a => {
            const location = a.Location || '--';
            const timeStr = a.CreatTime ? a.CreatTime.substring(11, 19) : '--';
            snapshotsHtml += `
            <div class="w-40 shrink-0 rounded-xl bg-slate-950/40 border border-rose-500/35 p-1.5 flex flex-col gap-1 shadow-[0_0_10px_rgba(244,63,94,0.12)] hover:border-rose-500 hover:shadow-[0_0_15px_rgba(244,63,94,0.25)] transition duration-300 cursor-pointer" onclick="showAlarmDetail(${a.Id})">
              <div class="relative aspect-video rounded-lg overflow-hidden border border-rose-500/20">
                <img src="${a.Picture}" class="w-full h-full object-cover">
                <span class="absolute bottom-1 right-1 bg-rose-600/90 text-white text-[8px] font-bold px-1.5 py-0.5 rounded shadow shadow-rose-950/50 tracking-wider">疑似火灾</span>
              </div>
              <div class="flex flex-col gap-0.5 px-0.5">
                <div class="flex justify-between items-center text-[9px]">
                  <span class="text-orange-400 font-mono font-semibold">${timeStr}</span>
                  <span class="text-slate-400 truncate max-w-[70px] font-medium">${location}</span>
                </div>
              </div>
            </div>`;
          });
          snapshotsContainer.innerHTML = snapshotsHtml;
        }
      }

      // Update Right Ranking List (monthly_ranking)
      const rankingList = document.getElementById('rankingList');
      if (rankingList && data.monthly_ranking) {
        if (data.monthly_ranking.length === 0) {
          rankingList.innerHTML = '<div class="flex items-center justify-center h-full text-slate-655 text-xs">暂无数据</div>';
        } else {
          let rankingHtml = '';
          const maxRank = data.max_rank || 1;
          data.monthly_ranking.forEach(item => {
            const percentage = Math.round((item.count / maxRank) * 100);
            rankingHtml += `
            <div class="flex flex-col gap-1.5">
              <div class="flex justify-between text-[11px] font-medium">
                <span class="text-slate-300">${item.name}</span>
                <span class="text-amber-400 font-semibold">${item.count} 次</span>
              </div>
              <div class="h-2 w-full bg-slate-950/60 rounded-full overflow-hidden border border-slate-800/40">
                <div class="h-full bg-gradient-to-r from-cyan-400 to-blue-500 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.3)]" style="width: ${percentage}%"></div>
              </div>
            </div>`;
          });
          rankingList.innerHTML = rankingHtml;
        }
      }

      // Update Charts
      if (data.time_stats && trendChartInstance) {
        const xData = data.time_stats.map(item => item.date.substring(5)); // 'MM-DD'
        const yData = data.time_stats.map(item => item.count);
        trendChartInstance.setOption({
          xAxis: { data: xData },
          series: [{ data: yData }]
        });
      }
    })
    .catch(err => console.error('Error fetching stats:', err));
}

// Window resizing for ECharts responsive
window.addEventListener('resize', function() {
  if (trendChartInstance) trendChartInstance.resize();
});

// Initialization
document.addEventListener("DOMContentLoaded", function() {
  const trendDom = document.getElementById('trendChart');
  if (trendDom) {
    trendChartInstance = echarts.init(trendDom);
    trendChartInstance.setOption(trendOption);
  }
  
  fetchRealtimeData();
  setInterval(fetchRealtimeData, 2000);
});
</script>

<!-- Alarm Detail Modal -->
<div id="detailModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-fade-in">
  <div class="glass-panel w-full max-w-2xl rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col max-h-[90vh] animate-scale-in">
    <!-- Modal Header -->
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
        预警事件详情
      </h3>
      <button onclick="closeAlarmDetail()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    
    <!-- Modal Body -->
    <div class="p-6 overflow-y-auto flex flex-col md:flex-row gap-6 text-xs scrollbar-thin">
      <!-- Left Side: Image & Video -->
      <div class="flex-1 flex flex-col gap-4 animate-fade-in">
        <div class="flex flex-col gap-1.5">
          <span class="text-slate-400 font-semibold">现场图片</span>
          <div class="aspect-video bg-slate-950/50 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center relative">
            <img id="modalAlarmImage" src="" class="w-full h-full object-cover hidden">
            <div id="modalAlarmNoImage" class="text-slate-500 flex flex-col items-center gap-1.5 py-8">
              <svg class="w-8 h-8 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
              </svg>
              <span>暂无现场图片</span>
            </div>
          </div>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-slate-400 font-semibold">视频回放</span>
          <div class="aspect-video bg-slate-950/50 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center relative">
            <video id="modalAlarmVideo" src="" class="w-full h-full object-cover hidden" controls autoplay muted></video>
            <div id="modalAlarmNoVideo" class="text-slate-500 flex flex-col items-center gap-1.5 py-8">
              <svg class="w-8 h-8 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
              </svg>
              <span>暂无录像视频</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Right Side: Info & Form -->
      <div class="flex-1 flex flex-col gap-4">
        <!-- Event Metadata -->
        <div class="bg-slate-905/30 border border-slate-800 rounded-xl p-4 flex flex-col gap-2.5">
          <div class="flex justify-between items-center border-b border-slate-800/60 pb-2">
            <span class="text-slate-400">发生地点</span>
            <span class="font-semibold text-slate-200" id="modalAlarmLocation">--</span>
          </div>
          <div class="flex justify-between items-center border-b border-slate-800/60 pb-2">
            <span class="text-slate-400">预警时间</span>
            <span class="font-mono text-slate-300" id="modalAlarmTime">--</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-slate-400">预警状态</span>
            <span id="modalAlarmStatus" class="font-bold">--</span>
          </div>
        </div>
        
        <!-- Processing Form (For Status = '1') -->
        <form id="modalProcessForm" method="post" action="" class="hidden flex flex-col gap-3">
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">紧急程度</label>
            <select name="UrgencyDegree" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
              <option value="普通">普通</option>
              <option value="紧急">紧急</option>
              <option value="特急">特急</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">处理结果</label>
            <select name="OperateResult" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
              <option value="火灾已确认并报警">火灾已确认并报警</option>
              <option value="误报无需处理">误报无需处理</option>
              <option value="其它已处理">其它已处理</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">处理备注 / 描述</label>
            <textarea name="Description" id="processDescription" rows="2" placeholder="请输入处理备注信息..." class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition resize-none"></textarea>
          </div>
          <div class="flex gap-2.5 mt-2">
            <button type="submit" class="flex-1 bg-rose-600/90 hover:bg-rose-600 text-white py-2 rounded-lg font-bold transition active:scale-95 shadow-md shadow-rose-950/50">确认处理</button>
            <button type="button" onclick="closeAlarmDetail()" class="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 rounded-lg font-semibold transition active:scale-95 border border-slate-700">暂不处理</button>
          </div>
        </form>
        
        <!-- Processed Information (For Status = '2' or '3') -->
        <div id="modalProcessedInfo" class="hidden flex flex-col gap-3 bg-slate-900/20 border border-slate-800/40 rounded-xl p-3.5 text-[11px] text-slate-300">
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理人</span>
            <span class="font-medium text-slate-200" id="modalInfoOperator">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理时间</span>
            <span class="font-mono text-slate-200" id="modalInfoTime">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理结果</span>
            <span class="font-medium text-orange-400" id="modalInfoResult">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">紧急程度</span>
            <span class="font-semibold text-rose-450" id="modalInfoUrgency">--</span>
          </div>
          <div class="flex flex-col gap-1">
            <span class="text-slate-400">备注描述</span>
            <p class="text-slate-350 leading-relaxed bg-slate-950/40 rounded-lg p-2 border border-slate-850" id="modalInfoDesc">--</p>
          </div>
          
          <!-- Audit Section for Status '2' and authorized users -->
          {% if user.RoleName in ['超级管理员', '审核人'] %}
          <div id="modalAuditActions" class="hidden flex gap-2 mt-2">
            <a id="modalAuditApproveBtn" href="" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-center py-2 rounded-lg font-semibold transition active:scale-95 shadow-md shadow-emerald-950/30">审核通过</a>
            <a id="modalAuditRejectBtn" href="" class="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-center py-2 rounded-lg font-semibold transition active:scale-95 shadow-md shadow-rose-950/30">驳回</a>
          </div>
          {% endif %}
          
          <button type="button" onclick="closeAlarmDetail()" class="w-full bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 rounded-lg font-semibold transition mt-2">关闭</button>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""

def make_admin_template(title, content_html, active_menu):
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>""" + title + """ - 视频AI智能识别平台</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://lib.baomitu.com/jquery/3.6.0/jquery.min.js"></script>
  <style>
    .scrollbar-thin::-webkit-scrollbar { width: 6px; height: 6px; }
    .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
    .scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
    .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
    .glass-panel {
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.06);
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes scaleIn {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }
    .animate-fade-in {
      animation: fadeIn 0.2s ease-out forwards;
    }
    .animate-scale-in {
      animation: scaleIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }
  </style>
</head>
<body class="bg-gradient-to-tr from-[#030712] via-[#091124] to-[#030712] text-slate-100 min-h-screen flex flex-col font-sans">
""" + BASE_NAV + """
<div class="flex flex-1 min-h-[calc(100vh-56px)]">
  <!-- Sidebar -->
  <aside class="w-64 bg-slate-950/40 border-r border-slate-900 p-5 shrink-0 flex flex-col gap-6 backdrop-blur-md">
    {% if user.RoleName == '超级管理员' %}
    <div class="flex flex-col gap-1.5">
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider px-2">资源管理</div>
      <div class="flex flex-col gap-0.5">
        <a href="/admin/device" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'device' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>💻</span> AI分析盒管理
        </a>
        <a href="/admin/camera" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'camera' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>📷</span> 摄像头管理
        </a>
      </div>
    </div>
    {% endif %}
    
    <div class="flex flex-col gap-1.5">
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider px-2">事件处理</div>
      <div class="flex flex-col gap-0.5">
        <a href="/admin/alarm" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'alarm' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>🚨</span> 报警事件
        </a>
        <a href="/admin/audit" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'audit' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>🛡️</span> 事件处理审核
        </a>
      </div>
    </div>
    
    {% if user.RoleName == '超级管理员' %}
    <div class="flex flex-col gap-1.5">
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider px-2">系统设置</div>
      <div class="flex flex-col gap-0.5">
        <a href="/admin/config" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'config' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>⚙️</span> 系统参数配置
        </a>
        <a href="/admin/branch" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'branch' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>🏢</span> 部门/机构管理
        </a>
        <a href="/admin/user" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'user' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>👤</span> 用户账户管理
        </a>
        <a href="/admin/role" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'role' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>🔑</span> 角色权限管理
        </a>
        <a href="/admin/dictionary" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'dictionary' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>📖</span> 数据字典项
        </a>
      </div>
    </div>
    
    <div class="flex flex-col gap-1.5">
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider px-2">故障与日志</div>
      <div class="flex flex-col gap-0.5">
        <a href="/admin/camera_error" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'camera_error' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>⚠️</span> 摄像头故障
        </a>
        <a href="/admin/device_error" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'device_error' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>📦</span> AI分析盒故障
        </a>
        <a href="/admin/log/access" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'access_log' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>🔒</span> 访问安全日志
        </a>
        <a href="/admin/log/operate" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition """ + ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_menu == 'operate_log' else 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40') + """">
          <span>📝</span> 业务操作日志
        </a>
      </div>
    </div>
    {% endif %}
  </aside>

  <!-- Main Content -->
  <main class="flex-1 p-6 overflow-y-auto scrollbar-thin">
    """ + content_html + """
  </main>
</div>
</body>
</html>
"""

CONFIG_TEMPLATE = make_admin_template("系统参数配置", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      系统参数配置
    </h2>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <div class="glass-panel rounded-2xl p-6 shadow-xl max-w-3xl">
    <form method="post" class="flex flex-col gap-5">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">站点名称</label>
          <input type="text" name="Name" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.Name }}">
        </div>
        
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">烟雾检测conf阈值</label>
          <input type="number" step="0.01" name="thresh" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.thresh }}">
          <span class="text-[10px] text-slate-500">阈值越高越不容易报警，阈值越低越容易报警</span>
        </div>
        
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">图片/视频长 (宽度)</label>
          <input type="number" name="width" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.width }}">
        </div>
        
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">图片/视频宽 (高度)</label>
          <input type="number" name="height" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.height }}">
        </div>
        
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">视频秒数</label>
          <input type="number" name="video_times" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.video_times }}">
        </div>
        
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-bold text-slate-400">连接心跳时间 (小时)</label>
          <input type="number" name="heartBeat" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.heartBeat }}">
        </div>
        
        <div class="flex flex-col gap-1.5 md:col-span-2">
          <label class="text-xs font-bold text-slate-400">网络异常误差 (分钟)</label>
          <input type="number" name="exception_times" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="{{ site.exception_times }}">
        </div>
      </div>
      
      <div class="flex justify-end mt-2">
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-6 py-2 rounded-lg font-semibold transition active:scale-95">保存配置</button>
      </div>
    </form>
  </div>
</div>
""", "config")

BRANCH_TEMPLATE = make_admin_template("部门管理", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      部门/机构管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增部门
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">部门名称</th>
          <th class="px-4 py-3">上级部门</th>
          <th class="px-4 py-3">备注</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for b in branches %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ b.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ b.Name }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ b.ParentId }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ b.Remark or '--' }}</td>
          <td class="px-4 py-3.5 flex items-center gap-2">
            <button class="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="editBranch({{ b.Id }},'{{ b.Name }}',{{ b.ParentId }},'{{ b.Remark or '' }}')">修改</button>
            <a href="/admin/branch/delete/{{ b.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="5" class="px-4 py-8 text-center text-slate-500">暂无部门数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增部门
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/branch/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">部门名称</label>
        <input type="text" name="Name" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">上级部门ID</label>
        <input type="number" name="ParentId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="0">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">备注</label>
        <textarea name="Remark" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition resize-none" rows="2"></textarea>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<!-- Edit Modal -->
<div id="editModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        修改部门
      </h3>
      <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" id="editForm" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">部门名称</label>
        <input type="text" name="Name" id="eName" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">上级部门ID</label>
        <input type="number" name="ParentId" id="eParent" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">备注</label>
        <textarea name="Remark" id="eRemark" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition resize-none" rows="2"></textarea>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeEditModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
function closeEditModal() { document.getElementById('editModal').classList.add('hidden'); }
function editBranch(id,name,parent,remark){
  document.getElementById('editForm').action='/admin/branch/edit/'+id;
  document.getElementById('eName').value=name;
  document.getElementById('eParent').value=parent;
  document.getElementById('eRemark').value=remark;
  document.getElementById('editModal').classList.remove('hidden');
}
</script>
""", "branch")

USER_TEMPLATE = make_admin_template("用户管理", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      用户账户管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增用户
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">账号</th>
          <th class="px-4 py-3">姓名</th>
          <th class="px-4 py-3">部门</th>
          <th class="px-4 py-3">区域</th>
          <th class="px-4 py-3">角色</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for u in users %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ u.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ u.Account }}</td>
          <td class="px-4 py-3.5 text-slate-200">{{ u.Name }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ u.BranchName or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ u.AreaName or '--' }}</td>
          <td class="px-4 py-3.5"><span class="px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-[10px]">{{ u.RoleName or '--' }}</span></td>
          <td class="px-4 py-3.5 flex items-center gap-2">
            <button class="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="editUser({{ u.Id }},'{{ u.Account }}','{{ u.Name }}',{{ u.AreaId or 1 }},{{ u.BranchId or 1 }},'{{ u.RoleName }}')">修改</button>
            <a href="/admin/user/delete/{{ u.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="7" class="px-4 py-8 text-center text-slate-500">暂无用户数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增用户
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/user/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">账号</label>
        <input type="text" name="Account" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">姓名</label>
        <input type="text" name="Name" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">密码</label>
        <input type="password" name="Password" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">区域</label>
        <select name="AreaId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">部门</label>
        <select name="BranchId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for b in branches %}
          <option value="{{ b.Id }}">{{ b.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">角色</label>
        <select name="RoleId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for r in roles %}
          <option value="{{ r.Id }}">{{ r.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<!-- Edit Modal -->
<div id="editModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        修改用户
      </h3>
      <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" id="editForm" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">账号</label>
        <input type="text" name="Account" id="eAcc" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">姓名</label>
        <input type="text" name="Name" id="eName" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">新密码 (留空不修改)</label>
        <input type="password" name="Password" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">区域</label>
        <select name="AreaId" id="eArea" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">部门</label>
        <select name="BranchId" id="eBranch" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for b in branches %}
          <option value="{{ b.Id }}">{{ b.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">角色</label>
        <select name="RoleId" id="eRole" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for r in roles %}
          <option value="{{ r.Id }}">{{ r.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeEditModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
function closeEditModal() { document.getElementById('editModal').classList.add('hidden'); }
function editUser(id,acc,name,area,branch,roleName){
  document.getElementById('editForm').action='/admin/user/edit/'+id;
  document.getElementById('eAcc').value=acc;
  document.getElementById('eName').value=name;
  document.getElementById('eArea').value=area;
  document.getElementById('eBranch').value=branch;
  Array.from(document.getElementById('eRole').options).forEach(function(o){
    o.selected = o.text === roleName;
  });
  document.getElementById('editModal').classList.remove('hidden');
}
</script>
""", "user")

ROLE_TEMPLATE = make_admin_template("角色管理", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      角色权限管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增角色
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">角色名</th>
          <th class="px-4 py-3">描述</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for r in roles %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ r.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ r.Name }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ r.Description or '--' }}</td>
          <td class="px-4 py-3.5">
            <a href="/admin/role/delete/{{ r.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="4" class="px-4 py-8 text-center text-slate-500">暂无角色数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-lg rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增角色
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/role/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">角色名</label>
        <input type="text" name="Name" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">描述</label>
        <textarea name="Description" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition resize-none" rows="2"></textarea>
      </div>
      <div class="flex flex-col gap-2">
        <label class="text-slate-400 font-medium">权限分配</label>
        <div class="grid grid-cols-2 gap-2 bg-slate-950/50 border border-slate-900 rounded-xl p-3.5">
          {% set all_auths = ['system_config','department','user','role','device','camera','alarm','audit','log','dashboard','dictionary'] %}
          {% set auth_names = {'system_config':'系统配置','department':'部门管理','user':'用户管理','role':'角色管理','device':'AI分析盒','camera':'摄像头','alarm':'报警事件','audit':'事件审核','log':'日志管理','dashboard':'数据大屏','dictionary':'数据字典'} %}
          {% for a in all_auths %}
          <label class="flex items-center gap-2 text-slate-300 hover:text-slate-100 transition cursor-pointer select-none">
            <input type="checkbox" name="authorities" value="{{ a }}" class="rounded border-slate-800 bg-slate-950 text-cyan-500 focus:ring-cyan-500/50">
            <span>{{ auth_names.get(a, a) }}</span>
          </label>
          {% endfor %}
        </div>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
</script>
""", "role")

DICT_TEMPLATE = make_admin_template("数据字典", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      数据字典管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增字典项
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">Key (类别键)</th>
          <th class="px-4 py-3">Value (字典值)</th>
          <th class="px-4 py-3">备注</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for it in items %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ it.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium font-mono">{{ it.Key }}</td>
          <td class="px-4 py-3.5 text-slate-200">{{ it.Value }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ it.Remark or '--' }}</td>
          <td class="px-4 py-3.5">
            <a href="/admin/dictionary/delete/{{ it.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="5" class="px-4 py-8 text-center text-slate-500">暂无数据字典项</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增字典项
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/dictionary/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">Key</label>
        <input type="text" name="Key" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">Value</label>
        <input type="text" name="Value" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">备注</label>
        <input type="text" name="Remark" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
</script>
""", "dictionary")

DEVICE_TEMPLATE = make_admin_template("AI分析盒管理", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      AI分析盒管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增AI分析盒
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">MAC地址</th>
          <th class="px-4 py-3">物理位置</th>
          <th class="px-4 py-3">所属区域</th>
          <th class="px-4 py-3">模型版本</th>
          <th class="px-4 py-3">最后通信时间</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for d in devices %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ d.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium font-mono">{{ d.MAC }}</td>
          <td class="px-4 py-3.5 text-slate-300">{{ d.Address or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ d.AreaName or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono text-[11px]">{{ d.ModelInfo or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ d.LastConnectTime or '--' }}</td>
          <td class="px-4 py-3.5 flex items-center gap-2">
            <button class="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="editDevice({{ d.Id }},'{{ d.MAC or '' }}','{{ d.Longitude or '' }}','{{ d.Latitude or '' }}','{{ d.Address or '' }}',{{ d.AreaId or 1 }},'{{ d.ModelInfo or '' }}')">修改</button>
            <a href="/admin/device/delete/{{ d.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="7" class="px-4 py-8 text-center text-slate-500">暂无AI分析盒数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增AI分析盒
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/device/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">MAC地址</label>
        <input type="text" name="MAC" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">经度</label>
          <input type="text" name="Longitude" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">纬度</label>
          <input type="text" name="Latitude" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">安装位置</label>
        <input type="text" name="Address" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">所属区域</label>
        <select name="AreaId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">模型信息</label>
        <input type="text" name="ModelInfo" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" value="YOLOv11-Fire">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">维护负责人</label>
        <input type="text" name="Maintainer" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<!-- Edit Modal -->
<div id="editModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        修改AI分析盒
      </h3>
      <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" id="editForm" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">MAC地址</label>
        <input type="text" name="MAC" id="eMAC" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">经度</label>
          <input type="text" name="Longitude" id="eLng" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">纬度</label>
          <input type="text" name="Latitude" id="eLat" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">安装位置</label>
        <input type="text" name="Address" id="eAddr" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">所属区域</label>
        <select name="AreaId" id="eArea" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">模型信息</label>
        <input type="text" name="ModelInfo" id="eModel" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeEditModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
function closeEditModal() { document.getElementById('editModal').classList.add('hidden'); }
function editDevice(id,mac,lng,lat,addr,area,model){
  document.getElementById('editForm').action='/admin/device/edit/'+id;
  document.getElementById('eMAC').value=mac;
  document.getElementById('eLng').value=lng;
  document.getElementById('eLat').value=lat;
  document.getElementById('eAddr').value=addr;
  document.getElementById('eArea').value=area;
  document.getElementById('eModel').value=model;
  document.getElementById('editModal').classList.remove('hidden');
}
</script>
""", "device")

CAMERA_TEMPLATE = make_admin_template("摄像头管理", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      摄像头管理
    </h2>
    <button onclick="openAddModal()" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition active:scale-95 flex items-center gap-1.5 text-xs">
      <span>➕</span> 新增摄像头
    </button>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">摄像头名称</th>
          <th class="px-4 py-3">IP地址</th>
          <th class="px-4 py-3">MAC地址</th>
          <th class="px-4 py-3">安装区域</th>
          <th class="px-4 py-3">设备型号</th>
          <th class="px-4 py-3">关联AI盒子</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for c in cameras %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ c.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ c.Name }}</td>
          <td class="px-4 py-3.5 text-slate-300 font-mono">{{ c.IP or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ c.MAC or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ c.AreaName or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ c.Type }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono text-[11px]">{{ c.DeviceMAC or '--' }}</td>
          <td class="px-4 py-3.5 flex items-center gap-2">
            <button class="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="editCam({{ c.Id }},'{{ c.IP or '' }}','{{ c.MAC or '' }}','{{ c.CameraUrl or '' }}','{{ c.Name or '' }}','{{ c.Longitude or '' }}','{{ c.Latitude or '' }}',{{ c.AreaId or 1 }},'{{ c.Type or '' }}',{{ c.DeviceId or 1 }})">修改</button>
            <a href="/admin/camera/delete/{{ c.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="return confirm('确认删除?')">删除</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="8" class="px-4 py-8 text-center text-slate-500">暂无摄像头数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Modal -->
<div id="addModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
        新增摄像头
      </h3>
      <button onclick="closeAddModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" action="/admin/camera/add" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">摄像头名称</label>
        <input type="text" name="Name" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">IP地址</label>
          <input type="text" name="IP" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">MAC地址</label>
          <input type="text" name="MAC" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">流媒体地址 / URL</label>
        <input type="text" name="CameraUrl" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">经度</label>
          <input type="text" name="Longitude" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">纬度</label>
          <input type="text" name="Latitude" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">区域</label>
        <select name="AreaId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">型号品牌</label>
        <select name="Type" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          <option>海康威视</option>
          <option>大华</option>
          <option>宇视</option>
          <option>其他</option>
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">关联AI分析盒</label>
        <select name="DeviceId" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for d in devices %}
          <option value="{{ d.Id }}">{{ d.MAC }} - {{ d.Address or 'N/A' }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeAddModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<!-- Edit Modal -->
<div id="editModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
  <div class="glass-panel w-full max-w-md rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col">
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        修改摄像头
      </h3>
      <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    <form method="post" id="editForm" class="p-6 flex flex-col gap-4 text-xs">
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">摄像头名称</label>
        <input type="text" name="Name" id="eName" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition" required>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">IP地址</label>
          <input type="text" name="IP" id="eIP" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">MAC地址</label>
          <input type="text" name="MAC" id="eMAC" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">流媒体地址 / URL</label>
        <input type="text" name="CameraUrl" id="eUrl" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">经度</label>
          <input type="text" name="Longitude" id="eLng" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-slate-400 font-medium">纬度</label>
          <input type="text" name="Latitude" id="eLat" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">区域</label>
        <select name="AreaId" id="eArea" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for a in areas %}
          <option value="{{ a.Id }}">{{ a.Name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">型号品牌</label>
        <select name="Type" id="eType" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          <option>海康威视</option>
          <option>大华</option>
          <option>宇视</option>
          <option>其他</option>
        </select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-slate-400 font-medium">关联AI分析盒</label>
        <select name="DeviceId" id="eDevice" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
          {% for d in devices %}
          <option value="{{ d.Id }}">{{ d.MAC }} - {{ d.Address or 'N/A' }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="flex justify-end gap-2.5 mt-2">
        <button type="button" onclick="closeEditModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition">取消</button>
        <button type="submit" class="bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-400 px-4 py-2 rounded-lg font-semibold transition">保存</button>
      </div>
    </form>
  </div>
</div>

<script>
function openAddModal() { document.getElementById('addModal').classList.remove('hidden'); }
function closeAddModal() { document.getElementById('addModal').classList.add('hidden'); }
function closeEditModal() { document.getElementById('editModal').classList.add('hidden'); }
function editCam(id,ip,mac,url,name,lng,lat,area,type,did){
  document.getElementById('editForm').action='/admin/camera/edit/'+id;
  document.getElementById('eName').value=name;
  document.getElementById('eIP').value=ip;
  document.getElementById('eMAC').value=mac;
  document.getElementById('eUrl').value=url;
  document.getElementById('eLng').value=lng;
  document.getElementById('eLat').value=lat;
  document.getElementById('eArea').value=area;
  document.getElementById('eType').value=type;
  document.getElementById('eDevice').value=did;
  document.getElementById('editModal').classList.remove('hidden');
}
</script>
""", "camera")

ALARM_TEMPLATE = make_admin_template("报警事件", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-rose-500 rounded-full shadow-[0_0_8px_#f43f5e]"></span>
      报警事件管理
    </h2>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Search / Filter Panel -->
  <div class="glass-panel rounded-xl p-4 shadow-md flex flex-wrap gap-4 items-end text-xs border border-slate-800/60">
    <div class="flex flex-col gap-1.5 min-w-[150px] flex-1">
      <label class="text-slate-400 font-medium">发生地点 / 相机</label>
      <input type="text" id="filterLocCam" placeholder="输入地点或相机名称..." class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 transition">
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-slate-400 font-medium">开始时间</label>
      <input type="datetime-local" id="filterStart" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-slate-400 font-medium">结束时间</label>
      <input type="datetime-local" id="filterEnd" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
    </div>
    <div class="flex flex-col gap-1.5 min-w-[120px]">
      <label class="text-slate-400 font-medium">预警状态</label>
      <select id="filterStatus" class="bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
        <option value="">全部</option>
        <option value="1">报警 (未处理)</option>
        <option value="2">待审核</option>
        <option value="3">已审核</option>
      </select>
    </div>
    <div class="flex gap-2 min-w-[150px]">
      <button onclick="applyFilters()" class="flex-1 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 py-1.5 rounded-lg font-semibold transition active:scale-95">筛选</button>
      <button onclick="clearFilters()" class="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 py-1.5 rounded-lg font-semibold transition active:scale-95">重置</button>
    </div>
  </div>

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">现场抓图</th>
          <th class="px-4 py-3">物理位置</th>
          <th class="px-4 py-3">关联摄像头</th>
          <th class="px-4 py-3">报警时间</th>
          <th class="px-4 py-3">报警状态</th>
          <th class="px-4 py-3">处理人</th>
          <th class="px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for a in alarms %}
        <tr class="hover:bg-slate-900/10 transition duration-150 border-b border-slate-900 cursor-pointer" id="alarm-row-{{ a.Id }}" data-id="{{ a.Id }}" onclick="showAlarmDetail({{ a.Id }})">
          <td class="px-4 py-3 text-slate-400 font-mono">{{ a.Id }}</td>
          <td class="px-4 py-3">
            {% if a.Picture %}
            <div class="w-16 h-10 rounded-md overflow-hidden border border-slate-800 cursor-pointer hover:border-cyan-500/50 transition" onclick="showAlarmDetail({{ a.Id }})">
              <img src="{{ a.Picture }}" class="w-full h-full object-cover">
            </div>
            {% else %}
            <span class="text-slate-600">--</span>
            {% endif %}
          </td>
          <td class="px-4 py-3 text-slate-200 font-medium alarm-location">{{ a.Location or '--' }}</td>
          <td class="px-4 py-3 text-slate-300 alarm-camera">{{ a.CameraName or '--' }}</td>
          <td class="px-4 py-3 text-slate-400 font-mono alarm-time">{{ a.CreatTime }}</td>
          <td class="px-4 py-3 alarm-status" data-status="{{ a.Status }}">
            {% if a.Status=='1' %}
            <span class="px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-455 border border-rose-500/20 text-[10px] font-bold">报警 (未处理)</span>
            {% elif a.Status=='2' %}
            <span class="px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-semibold">待审核</span>
            {% elif a.Status=='3' %}
            <span class="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-semibold">已审核</span>
            {% endif %}
          </td>
          <td class="px-4 py-3 text-slate-400">{{ a.OperatorName or '--' }}</td>
          <td class="px-4 py-3 flex items-center gap-2">
            <button class="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 text-cyan-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="showAlarmDetail({{ a.Id }})">详情</button>
            {% if a.Status=='1' %}
            <button class="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95" onclick="showAlarmDetail({{ a.Id }})">处理</button>
            {% endif %}
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="8" class="px-4 py-8 text-center text-slate-500">暂无报警事件数据</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Alarm Detail Modal -->
<div id="detailModal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-fade-in">
  <div class="glass-panel w-full max-w-2xl rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-slate-700/50 overflow-hidden flex flex-col max-h-[90vh] animate-scale-in">
    <!-- Modal Header -->
    <div class="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/40">
      <h3 class="text-sm font-bold text-slate-100 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
        预警事件详情
      </h3>
      <button onclick="closeAlarmDetail()" class="text-slate-400 hover:text-slate-200 transition text-lg">&times;</button>
    </div>
    
    <!-- Modal Body -->
    <div class="p-6 overflow-y-auto flex flex-col md:flex-row gap-6 text-xs scrollbar-thin">
      <!-- Left Side: Image & Video -->
      <div class="flex-1 flex flex-col gap-4 animate-fade-in">
        <div class="flex flex-col gap-1.5">
          <span class="text-slate-400 font-semibold">现场图片</span>
          <div class="aspect-video bg-slate-950/50 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center relative">
            <img id="modalAlarmImage" src="" class="w-full h-full object-cover hidden">
            <div id="modalAlarmNoImage" class="text-slate-500 flex flex-col items-center gap-1.5 py-8">
              <svg class="w-8 h-8 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
              </svg>
              <span>暂无现场图片</span>
            </div>
          </div>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-slate-400 font-semibold">视频回放</span>
          <div class="aspect-video bg-slate-950/50 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center relative">
            <video id="modalAlarmVideo" src="" class="w-full h-full object-cover hidden" controls autoplay muted></video>
            <div id="modalAlarmNoVideo" class="text-slate-500 flex flex-col items-center gap-1.5 py-8">
              <svg class="w-8 h-8 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
              </svg>
              <span>暂无录像视频</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Right Side: Info & Form -->
      <div class="flex-1 flex flex-col gap-4">
        <!-- Event Metadata -->
        <div class="bg-slate-905/30 border border-slate-800 rounded-xl p-4 flex flex-col gap-2.5">
          <div class="flex justify-between items-center border-b border-slate-800/60 pb-2">
            <span class="text-slate-400">发生地点</span>
            <span class="font-semibold text-slate-200" id="modalAlarmLocation">--</span>
          </div>
          <div class="flex justify-between items-center border-b border-slate-800/60 pb-2">
            <span class="text-slate-400">预警时间</span>
            <span class="font-mono text-slate-300" id="modalAlarmTime">--</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-slate-400">预警状态</span>
            <span id="modalAlarmStatus" class="font-bold">--</span>
          </div>
        </div>
        
        <!-- Processing Form (For Status = '1') -->
        <form id="modalProcessForm" method="post" action="" class="hidden flex flex-col gap-3">
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">紧急程度</label>
            <select name="UrgencyDegree" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
              <option value="普通">普通</option>
              <option value="紧急">紧急</option>
              <option value="特急">特急</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">处理结果</label>
            <select name="OperateResult" class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500/50 transition">
              <option value="火灾已确认并报警">火灾已确认并报警</option>
              <option value="误报无需处理">误报无需处理</option>
              <option value="其它已处理">其它已处理</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-slate-400 font-medium">处理备注 / 描述</label>
            <textarea name="Description" id="processDescription" rows="2" placeholder="请输入处理备注信息..." class="w-full bg-slate-950/50 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition resize-none"></textarea>
          </div>
          <div class="flex gap-2.5 mt-2">
            <button type="submit" class="flex-1 bg-rose-600/90 hover:bg-rose-600 text-white py-2 rounded-lg font-bold transition active:scale-95 shadow-md shadow-rose-950/50">确认处理</button>
            <button type="button" onclick="closeAlarmDetail()" class="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 rounded-lg font-semibold transition active:scale-95 border border-slate-700">暂不处理</button>
          </div>
        </form>
        
        <!-- Processed Information (For Status = '2' or '3') -->
        <div id="modalProcessedInfo" class="hidden flex flex-col gap-3 bg-slate-900/20 border border-slate-800/40 rounded-xl p-3.5 text-[11px] text-slate-300">
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理人</span>
            <span class="font-medium text-slate-200" id="modalInfoOperator">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理时间</span>
            <span class="font-mono text-slate-200" id="modalInfoTime">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">处理结果</span>
            <span class="font-medium text-orange-400" id="modalInfoResult">--</span>
          </div>
          <div class="flex justify-between border-b border-slate-800/60 pb-1.5">
            <span class="text-slate-400">紧急程度</span>
            <span class="font-semibold text-rose-450" id="modalInfoUrgency">--</span>
          </div>
          <div class="flex flex-col gap-1">
            <span class="text-slate-400">备注描述</span>
            <p class="text-slate-350 leading-relaxed bg-slate-950/40 rounded-lg p-2 border border-slate-850" id="modalInfoDesc">--</p>
          </div>
          
          <!-- Audit Section for Status '2' and authorized users -->
          {% if user.RoleName in ['超级管理员', '审核人'] %}
          <div id="modalAuditActions" class="hidden flex gap-2 mt-2">
            <a id="modalAuditApproveBtn" href="" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-center py-2 rounded-lg font-semibold transition active:scale-95 shadow-md shadow-emerald-950/30">审核通过</a>
            <a id="modalAuditRejectBtn" href="" class="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-center py-2 rounded-lg font-semibold transition active:scale-95 shadow-md shadow-rose-950/30">驳回</a>
          </div>
          {% endif %}
          
          <button type="button" onclick="closeAlarmDetail()" class="w-full bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 rounded-lg font-semibold transition mt-2">关闭</button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// Serialize alarm data to JavaScript object dictionary to avoid escaping problems
const alarmData = {
  {% for a in alarms %}
  "{{ a.Id }}": {
    id: {{ a.Id }},
    time: "{{ a.CreatTime or '' }}",
    location: "{{ (a.Location or a.CameraName or '未知位置')|replace('\\\\', '\\\\\\\\')|replace('"', '\\"') }}",
    picture: "{{ a.Picture or '' }}",
    videoUrl: "{{ a.VideoUrl or '' }}",
    status: "{{ a.Status }}",
    desc: "{{ (a.Description or '')|replace('\\\\', '\\\\\\\\')|replace('"', '\\"')|replace('\r', '')|replace('\n', '\\n') }}",
    urgency: "{{ a.UrgencyDegree or '' }}",
    result: "{{ a.OperateResult or '' }}",
    operator: "{{ a.OperatorName or '' }}",
    operateTime: "{{ a.OperateTime or '' }}"
  },
  {% endfor %}
};

function showAlarmDetail(id) {
  const a = alarmData[id];
  if (!a) return;

  document.getElementById('modalProcessForm').action = '/admin/alarm/process/' + id;
  document.getElementById('modalAlarmTime').textContent = a.time || '--';
  document.getElementById('modalAlarmLocation').textContent = a.location || '未知位置';
  
  // Picture
  const img = document.getElementById('modalAlarmImage');
  const noImg = document.getElementById('modalAlarmNoImage');
  if (a.picture) {
    img.src = a.picture;
    img.classList.remove('hidden');
    noImg.classList.add('hidden');
  } else {
    img.src = '';
    img.classList.add('hidden');
    noImg.classList.remove('hidden');
  }
  
  // Video
  const video = document.getElementById('modalAlarmVideo');
  const noVideo = document.getElementById('modalAlarmNoVideo');
  if (a.videoUrl) {
    video.src = a.videoUrl;
    video.classList.remove('hidden');
    noVideo.classList.add('hidden');
  } else {
    video.src = '';
    video.classList.add('hidden');
    noVideo.classList.remove('hidden');
  }

  const statusEl = document.getElementById('modalAlarmStatus');
  if (a.status === '1') {
    statusEl.textContent = '报警 (未处理)';
    statusEl.className = 'text-rose-450 font-bold';
    document.getElementById('modalProcessForm').classList.remove('hidden');
    document.getElementById('modalProcessedInfo').classList.add('hidden');
  } else {
    const statusText = a.status === '2' ? '待审核' : '已审核';
    statusEl.textContent = statusText;
    statusEl.className = a.status === '2' ? 'text-amber-450 font-bold' : 'text-emerald-450 font-bold';
    
    document.getElementById('modalProcessForm').classList.add('hidden');
    document.getElementById('modalProcessedInfo').classList.remove('hidden');
    
    document.getElementById('modalInfoOperator').textContent = a.operator || '系统/未知';
    document.getElementById('modalInfoTime').textContent = a.operateTime || '--';
    document.getElementById('modalInfoResult').textContent = a.result || '--';
    document.getElementById('modalInfoUrgency').textContent = a.urgency || '普通';
    document.getElementById('modalInfoDesc').textContent = a.desc || '无备注';
    
    const auditActions = document.getElementById('modalAuditActions');
    if (auditActions) {
      if (a.status === '2') {
        auditActions.classList.remove('hidden');
        document.getElementById('modalAuditApproveBtn').href = '/admin/audit/approve/' + id;
        document.getElementById('modalAuditRejectBtn').href = '/admin/audit/reject/' + id;
      } else {
        auditActions.classList.add('hidden');
      }
    }
  }

  document.getElementById('detailModal').classList.remove('hidden');
}

function closeAlarmDetail() {
  document.getElementById('detailModal').classList.add('hidden');
  const video = document.getElementById('modalAlarmVideo');
  if (video) {
    video.pause();
  }
}

// Client-side filtering logic
function applyFilters() {
  const locCam = document.getElementById('filterLocCam').value.toLowerCase();
  const start = document.getElementById('filterStart').value;
  const end = document.getElementById('filterEnd').value;
  const status = document.getElementById('filterStatus').value;
  
  const startMs = start ? new Date(start).getTime() : 0;
  const endMs = end ? new Date(end).getTime() : 0;
  
  document.querySelectorAll('tbody tr[id^="alarm-row-"]').forEach(row => {
    const id = row.getAttribute('data-id');
    const a = alarmData[id];
    if (!a) return;
    
    let show = true;
    
    if (locCam) {
      const loc = (a.location || '').toLowerCase();
      if (!loc.includes(locCam)) show = false;
    }
    
    if (status) {
      if (a.status !== status) show = false;
    }
    
    if (startMs || endMs) {
      if (a.time) {
        const timeMs = new Date(a.time.replace(' ', 'T')).getTime();
        if (startMs && timeMs < startMs) show = false;
        if (endMs && timeMs > endMs) show = false;
      } else {
        show = false;
      }
    }
    
    if (show) {
      row.classList.remove('hidden');
    } else {
      row.classList.add('hidden');
    }
  });
}

function clearFilters() {
  document.getElementById('filterLocCam').value = '';
  document.getElementById('filterStart').value = '';
  document.getElementById('filterEnd').value = '';
  document.getElementById('filterStatus').value = '';
  
  document.querySelectorAll('tbody tr[id^="alarm-row-"]').forEach(row => {
    row.classList.remove('hidden');
  });
}
</script>
""", "alarm")

AUDIT_TEMPLATE = make_admin_template("事件处理审核", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-emerald-500 rounded-full shadow-[0_0_8px_#10b981]"></span>
      事件处理审核
    </h2>
  </div>

  {% with msgs=get_flashed_messages() %}
  {% if msgs %}
  <div class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-3 rounded-xl text-xs font-semibold">
    {{ msgs[0] }}
  </div>
  {% endif %}
  {% endwith %}

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">物理位置</th>
          <th class="px-4 py-3">关联摄像头</th>
          <th class="px-4 py-3">报警时间</th>
          <th class="px-4 py-3">处理负责人</th>
          <th class="px-4 py-3">处理汇报</th>
          <th class="px-4 py-3">处理时间</th>
          <th class="px-4 py-3">操作选项</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for a in alarms %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ a.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ a.Location or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-300">{{ a.CameraName or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ a.CreatTime }}</td>
          <td class="px-4 py-3.5 text-slate-300 font-medium">{{ a.OperatorName or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-200">{{ a.OperateResult or '--' }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ a.OperateTime or '--' }}</td>
          <td class="px-4 py-3.5 flex items-center gap-2">
            <a href="/admin/audit/approve/{{ a.Id }}" class="bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-emerald-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95">审核通过</a>
            <a href="/admin/audit/reject/{{ a.Id }}" class="bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 px-2.5 py-1 rounded-md font-medium transition active:scale-95">驳回处理</a>
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="8" class="px-4 py-8 text-center text-slate-500">暂无待审核事件</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""", "audit")

CAMERA_ERROR_TEMPLATE = make_admin_template("摄像头故障日志", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-rose-500 rounded-full shadow-[0_0_8px_#f43f5e]"></span>
      摄像头故障日志
    </h2>
  </div>

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">故障摄像头</th>
          <th class="px-4 py-3">MAC地址</th>
          <th class="px-4 py-3">故障发生时间</th>
          <th class="px-4 py-3">故障特征码</th>
          <th class="px-4 py-3">故障详细描述</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for e in errors %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ e.CameraName or e.CameraId }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.MAC }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.CreateTime }}</td>
          <td class="px-4 py-3.5"><span class="px-2 py-0.5 rounded bg-rose-500/10 text-rose-455 border border-rose-500/20 font-mono text-[10px]">{{ e.ErrorCode }}</span></td>
          <td class="px-4 py-3.5 text-slate-300">{{ e.ErrorMsg or '--' }}</td>
        </tr>
        {% else %}
        <tr>
          <td colspan="6" class="px-4 py-8 text-center text-slate-500">暂无摄像头故障日志</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""", "camera_error")

DEVICE_ERROR_TEMPLATE = make_admin_template("AI分析盒故障日志", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-rose-500 rounded-full shadow-[0_0_8px_#f43f5e]"></span>
      AI分析盒故障日志
    </h2>
  </div>

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">故障设备</th>
          <th class="px-4 py-3">MAC地址</th>
          <th class="px-4 py-3">故障发生时间</th>
          <th class="px-4 py-3">故障特征码</th>
          <th class="px-4 py-3">故障详细描述</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for e in errors %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ e.DeviceAddress or e.DeviceId }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.DeviceMAC or e.MAC }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ e.CreateTime }}</td>
          <td class="px-4 py-3.5"><span class="px-2 py-0.5 rounded bg-rose-500/10 text-rose-455 border border-rose-500/20 font-mono text-[10px]">{{ e.ErrorCode }}</span></td>
          <td class="px-4 py-3.5 text-slate-300">{{ e.ErrorMsg or '--' }}</td>
        </tr>
        {% else %}
        <tr>
          <td colspan="6" class="px-4 py-8 text-center text-slate-500">暂无AI分析盒故障日志</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""", "device_error")

ACCESS_LOG_TEMPLATE = make_admin_template("访问安全日志", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      安全访问日志
    </h2>
  </div>

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">登录用户</th>
          <th class="px-4 py-3">登录时间</th>
          <th class="px-4 py-3">客户端IP</th>
          <th class="px-4 py-3">访问途径 / 登录方式</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for l in logs %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ l.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ l.UserName or l.UserId }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ l.LoginTime }}</td>
          <td class="px-4 py-3.5 text-slate-300 font-mono">{{ l.LoginInIp }}</td>
          <td class="px-4 py-3.5 text-slate-400">{{ l.LoginType }}</td>
        </tr>
        {% else %}
        <tr>
          <td colspan="5" class="px-4 py-8 text-center text-slate-500">暂无访问日志</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""", "access_log")

OPERATE_LOG_TEMPLATE = make_admin_template("操作日志", """
<div class="flex flex-col gap-6">
  <div class="flex justify-between items-center border-b border-slate-800 pb-4">
    <h2 class="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
      <span class="w-1.5 h-4.5 bg-cyan-500 rounded-full shadow-[0_0_8px_#06b6d4]"></span>
      业务操作日志
    </h2>
  </div>

  <!-- Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/30 shadow-xl">
    <table class="w-full text-left border-collapse text-xs">
      <thead>
        <tr class="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-semibold tracking-wider">
          <th class="px-4 py-3">ID</th>
          <th class="px-4 py-3">功能模块</th>
          <th class="px-4 py-3">操作类型</th>
          <th class="px-4 py-3">变更细节 / 内容</th>
          <th class="px-4 py-3">执行时间</th>
          <th class="px-4 py-3">操作执行人</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-900">
        {% for l in logs %}
        <tr class="hover:bg-slate-900/20 transition duration-150">
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ l.Id }}</td>
          <td class="px-4 py-3.5 text-slate-200 font-medium">{{ l.MenuName }}</td>
          <td class="px-4 py-3.5"><span class="px-2 py-0.5 rounded text-[10px] font-semibold {% if l.Type == '删除' %}bg-rose-500/10 text-rose-400 border border-rose-500/20{% elif l.Type == '修改' %}bg-amber-500/10 text-amber-400 border border-amber-500/20{% else %}bg-emerald-500/10 text-emerald-400 border border-emerald-500/20{% endif %}">{{ l.Type }}</span></td>
          <td class="px-4 py-3.5 text-slate-300 font-mono max-w-[300px] truncate" title="{{ l.ContentNew }}">{{ l.ContentNew }}</td>
          <td class="px-4 py-3.5 text-slate-400 font-mono">{{ l.CreateTime }}</td>
          <td class="px-4 py-3.5 text-slate-200">{{ l.UserName or l.UserId }}</td>
        </tr>
        {% else %}
        <tr>
          <td colspan="6" class="px-4 py-8 text-center text-slate-550">暂无操作日志</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""", "operate_log")



if __name__ == "__main__":
    init_db()
    logger.info("Starting Web Management Server...")
    logger.info("访问地址: http://0.0.0.0:5000")
    logger.info("管理员: admin / 123456")
    logger.info("处理人: chuli001 / 123456")
    app.run(host="0.0.0.0", port=5000, debug=True)
