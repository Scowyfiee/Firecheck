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
    reviewed_alarms = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE Status='3'").fetchone()["c"]
    total_cameras = db.execute("SELECT COUNT(*) as c FROM T_Camera").fetchone()["c"]
    total_devices = db.execute("SELECT COUNT(*) as c FROM T_Device").fetchone()["c"]
    offline_devices = db.execute("SELECT COUNT(*) as c FROM T_Device WHERE LastConnectTime < datetime('now','-6 hour')").fetchone()["c"]

    area_stats = [dict(r) for r in db.execute(
        "SELECT a.Name as area, COUNT(dr.Id) as count FROM T_Area a LEFT JOIN T_DetectResult dr ON a.Id=dr.AreaId GROUP BY a.Id").fetchall()]

    time_stats = [dict(r) for r in db.execute(
        "SELECT strftime('%Y-%m-%d', CreatTime) as date, COUNT(*) as count FROM T_DetectResult WHERE CreatTime > datetime('now','-30 day') GROUP BY date ORDER BY date").fetchall()]

    recent_alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, c.Name as CameraName, a.Name as AreaName, d.Address as DeviceAddress FROM T_DetectResult dr LEFT JOIN T_Camera c ON dr.CameraId=c.Id LEFT JOIN T_Area a ON dr.AreaId=a.Id LEFT JOIN T_Device d ON dr.DeviceId=d.Id ORDER BY dr.CreatTime DESC LIMIT 20").fetchall()]

    cameras = [dict(r) for r in db.execute(
        "SELECT c.*, a.Name as AreaName, d.MAC as DeviceMAC FROM T_Camera c LEFT JOIN T_Area a ON c.AreaId=a.Id LEFT JOIN T_Device d ON c.DeviceId=d.Id").fetchall()]

    camera_alarm_counts = {}
    for cam in cameras:
        cnt = db.execute("SELECT COUNT(*) as c FROM T_DetectResult WHERE CameraId=?", (cam["Id"],)).fetchone()["c"]
        camera_alarm_counts[cam["Id"]] = cnt

    return render_template_string(DASHBOARD_TEMPLATE, user=user,
                                  total_alarms=total_alarms, pending_alarms=pending_alarms,
                                  reviewed_alarms=reviewed_alarms, total_cameras=total_cameras,
                                  total_devices=total_devices, offline_devices=offline_devices,
                                  area_stats=json.dumps(area_stats), time_stats=json.dumps(time_stats),
                                  recent_alarms=recent_alarms, cameras=cameras, camera_alarm_counts=camera_alarm_counts)


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
    return redirect(url_for("alarm_list"))


# --- Routes: Event Audit ---

@app.route("/admin/audit")
@login_required
def audit_list():
    db = get_db()
    alarms = [dict(r) for r in db.execute(
        "SELECT dr.*, c.Name as CameraName, u.Name as OperatorName FROM T_DetectResult dr LEFT JOIN T_Camera c ON dr.CameraId=c.Id LEFT JOIN T_User u ON dr.OperateUserId=u.Id WHERE dr.Status='2' ORDER BY dr.OperateTime DESC").fetchall()]
    return render_template_string(AUDIT_TEMPLATE, user=get_current_user(), alarms=alarms)


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
    return jsonify({"area_stats": area, "time_stats": time_data, "total": total})


# --- Templates ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>视频AI智能识别及预警管理系统 - 登录</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<style>
body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); min-height:100vh; display:flex; align-items:center; justify-content:center; }
.login-box { background:rgba(255,255,255,0.95); border-radius:10px; padding:40px; width:400px; box-shadow:0 10px 40px rgba(0,0,0,0.3); }
.login-box h2 { text-align:center; color:#333; margin-bottom:30px; font-size:22px; }
.login-box .logo { text-align:center; margin-bottom:20px; font-size:48px; }
</style>
</head>
<body>
<div class="login-box">
    <div class="logo">&#128293;</div>
    <h2>视频AI智能识别及预警管理系统</h2>
    {% with msgs = get_flashed_messages() %}{% if msgs %}<div class="alert alert-danger">{{ msgs[0] }}</div>{% endif %}{% endwith %}
    <form method="post">
        <div class="form-group"><input type="text" name="account" class="form-control" placeholder="账号" required autofocus></div>
        <div class="form-group"><input type="password" name="password" class="form-control" placeholder="密码" required></div>
        <button type="submit" class="btn btn-danger btn-block" style="background:#e74c3c;border-color:#c0392b;">登 录</button>
    </form>
    <p class="text-muted text-center" style="margin-top:15px;font-size:12px;">管理员: admin/123456 | 处理人: chuli001/123456</p>
</div>
</body>
</html>
"""

BASE_NAV = """
<nav class="navbar navbar-inverse navbar-fixed-top" style="background:#1a1a2e;border:none;">
<div class="container-fluid">
<div class="navbar-header">
    <button type="button" class="navbar-toggle collapsed" data-toggle="collapse" data-target="#navbar">
        <span class="sr-only">菜单</span><span class="icon-bar"></span><span class="icon-bar"></span><span class="icon-bar"></span>
    </button>
    <a class="navbar-brand" href="/dashboard" style="color:#e74c3c;">&#128293; 火焰预警平台</a>
</div>
<div class="collapse navbar-collapse" id="navbar">
    <ul class="nav navbar-nav">
        <li><a href="/dashboard"><i class="glyphicon glyphicon-dashboard"></i> 数据大屏</a></li>
        {% if user.RoleName == '超级管理员' %}
        <li class="dropdown"><a href="#" class="dropdown-toggle" data-toggle="dropdown">系统设置 <span class="caret"></span></a>
            <ul class="dropdown-menu">
                <li><a href="/admin/config">系统配置</a></li>
                <li><a href="/admin/branch">部门管理</a></li>
                <li><a href="/admin/user">用户管理</a></li>
                <li><a href="/admin/role">角色管理</a></li>
                <li><a href="/admin/dictionary">数据字典</a></li>
            </ul>
        </li>
        <li class="dropdown"><a href="#" class="dropdown-toggle" data-toggle="dropdown">设备管理 <span class="caret"></span></a>
            <ul class="dropdown-menu">
                <li><a href="/admin/device">AI分析盒管理</a></li>
                <li><a href="/admin/camera">摄像头管理</a></li>
            </ul>
        </li>
        {% endif %}
        <li class="dropdown"><a href="#" class="dropdown-toggle" data-toggle="dropdown">报警事件 <span class="caret"></span></a>
            <ul class="dropdown-menu">
                <li><a href="/admin/alarm">报警事件</a></li>
                <li><a href="/admin/audit">事件处理审核</a></li>
                <li><a href="/admin/camera_error">摄像头故障</a></li>
                <li><a href="/admin/device_error">AI分析盒故障</a></li>
            </ul>
        </li>
        {% if user.RoleName == '超级管理员' %}
        <li class="dropdown"><a href="#" class="dropdown-toggle" data-toggle="dropdown">日志管理 <span class="caret"></span></a>
            <ul class="dropdown-menu">
                <li><a href="/admin/log/access">访问日志</a></li>
                <li><a href="/admin/log/operate">操作日志</a></li>
            </ul>
        </li>
        {% endif %}
    </ul>
    <ul class="nav navbar-nav navbar-right">
        <li><a href="#"><i class="glyphicon glyphicon-user"></i> {{ user.Name }} ({{ user.RoleName }})</a></li>
        <li><a href="/logout"><i class="glyphicon glyphicon-log-out"></i> 退出</a></li>
    </ul>
</div>
</div>
</nav>
<div style="padding-top:50px;"></div>
"""

DASHBOARD_TEMPLATE = BASE_NAV + """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><title>数据大屏 - 视频AI智能识别及预警管理系统</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>
body { background:#f0f2f5; font-family:"Microsoft YaHei",sans-serif; }
.stat-card { background:white; border-radius:8px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.1); text-align:center; }
.stat-card .num { font-size:36px; font-weight:bold; }
.stat-card .label-text { color:#999; font-size:14px; }
.stat-card.red { border-left:4px solid #e74c3c; }
.stat-card.orange { border-left:4px solid #f39c12; }
.stat-card.blue { border-left:4px solid #3498db; }
.stat-card.green { border-left:4px solid #27ae60; }
.stat-card.purple { border-left:4px solid #9b59b6; }
.panel { border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
.table>tbody>tr>td { vertical-align:middle; }
.alarm-image { max-width:80px; max-height:60px; border-radius:4px; cursor:pointer; }
.badge-status-1 { background:#e74c3c; }
.badge-status-2 { background:#f39c12; }
.badge-status-3 { background:#27ae60; }
</style>
</head>
<body>
<div class="container-fluid" style="margin-top:60px;">
    <h3 style="margin-bottom:20px;"><i class="glyphicon glyphicon-dashboard"></i> 数据大屏</h3>
    <div class="row">
        <div class="col-md-2 col-sm-4"><div class="stat-card red"><div class="num">{{ total_alarms }}</div><div class="label-text">总报警次数</div></div></div>
        <div class="col-md-2 col-sm-4"><div class="stat-card orange"><div class="num">{{ pending_alarms }}</div><div class="label-text">待处理报警</div></div></div>
        <div class="col-md-2 col-sm-4"><div class="stat-card green"><div class="num">{{ reviewed_alarms }}</div><div class="label-text">已审核报警</div></div></div>
        <div class="col-md-2 col-sm-4"><div class="stat-card blue"><div class="num">{{ total_cameras }}</div><div class="label-text">摄像头总数</div></div></div>
        <div class="col-md-2 col-sm-4"><div class="stat-card purple"><div class="num">{{ total_devices }}</div><div class="label-text">AI分析盒</div></div></div>
        <div class="col-md-2 col-sm-4"><div class="stat-card" style="border-left:4px solid #e67e22;"><div class="num">{{ offline_devices }}</div><div class="label-text">离线设备</div></div></div>
    </div>
    <div class="row">
        <div class="col-md-8">
            <div class="panel panel-default">
                <div class="panel-heading"><strong>摄像头分布地图</strong></div>
                <div class="panel-body"><div id="mapChart" style="height:420px;"></div></div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="panel panel-default">
                <div class="panel-heading"><strong>区域报警统计</strong></div>
                <div class="panel-body"><div id="areaChart" style="height:190px;"></div></div>
            </div>
            <div class="panel panel-default">
                <div class="panel-heading"><strong>近30天报警趋势</strong></div>
                <div class="panel-body"><div id="timeChart" style="height:190px;"></div></div>
            </div>
        </div>
    </div>
    <div class="row">
        <div class="col-md-12">
            <div class="panel panel-default">
                <div class="panel-heading"><strong>最新报警事件</strong> <a href="/admin/alarm" class="btn btn-xs btn-danger pull-right">查看全部</a></div>
                <div class="panel-body">
                    <table class="table table-striped table-hover">
                        <thead><tr><th>ID</th><th>图片</th><th>位置</th><th>摄像头</th><th>时间</th><th>状态</th><th>操作</th></tr></thead>
                        <tbody>
                        {% for a in recent_alarms %}
                        <tr>
                            <td>{{ a.Id }}</td>
                            <td>{% if a.Picture %}<img src="{{ a.Picture }}" class="alarm-image" onclick="window.open('{{ a.Picture }}')">{% else %}-{% endif %}</td>
                            <td>{{ a.Location or '-' }}</td>
                            <td>{{ a.CameraName or '-' }}</td>
                            <td>{{ a.CreatTime }}</td>
                            <td>
                                {% if a.Status == '1' %}<span class="badge badge-status-1">报警</span>
                                {% elif a.Status == '2' %}<span class="badge badge-status-2">待审核</span>
                                {% elif a.Status == '3' %}<span class="badge badge-status-3">已审核</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if a.VideoUrl %}<a href="{{ a.VideoUrl }}" target="_blank" class="btn btn-xs btn-info">视频</a>{% endif %}
                                <a href="{{ url_for('alarm_list') }}" class="btn btn-xs btn-warning">处理</a>
                            </td>
                        </tr>
                        {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>
<script>
var mapChart = echarts.init(document.getElementById('mapChart'));
var cameras = {{ cameras|tojson }};
var alarmCounts = {{ camera_alarm_counts|tojson }};
var mapData = cameras.map(function(c){
    var lng = parseFloat(c.Longitude) || 106.55;
    var lat = parseFloat(c.Latitude) || 29.56;
    return {name: c.Name, value: [lng, lat, alarmCounts[c.Id] || 0], area: c.AreaName, device: c.DeviceMAC};
});
mapChart.setOption({
    tooltip: {trigger:'item', formatter:function(p){return p.name+'<br/>报警次数:'+(p.value[2]||0)+'<br/>区域:'+(p.data.area||'');}},
    xAxis:{type:'value',name:'经度'},
    yAxis:{type:'value',name:'纬度'},
    series:[{type:'scatter',symbolSize:function(val){return Math.max(15, (val[2]||0)*5+15);},
        itemStyle:{color:'#e74c3c'},data:mapData,label:{show:true,formatter:'{b}',position:'top',fontSize:10}}]
});

var areaChart = echarts.init(document.getElementById('areaChart'));
areaChart.setOption({
    tooltip:{trigger:'item'},
    series:[{type:'pie',radius:['40%','70%'],data:{{ area_stats|safe }},label:{formatter:'{b}\\n{d}%'}}]
});

var timeChart = echarts.init(document.getElementById('timeChart'));
var timeData = {{ time_stats|safe }};
timeChart.setOption({
    tooltip:{trigger:'axis'},
    xAxis:{type:'category',data:timeData.map(function(d){return d.date;}),axisLabel:{rotate:45,fontSize:10}},
    yAxis:{type:'value'},
    series:[{type:'line',data:timeData.map(function(d){return d.count;}),smooth:true,areaStyle:{color:'rgba(231,76,60,0.2)'},lineStyle:{color:'#e74c3c'},itemStyle:{color:'#e74c3c'}}]
});

window.addEventListener('resize',function(){mapChart.resize();areaChart.resize();timeChart.resize();});
</script>
</body>
</html>
"""

CONFIG_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>系统配置</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}.panel{border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}</style></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>系统配置</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<div class="panel panel-default"><div class="panel-body">
<form method="post" class="form-horizontal">
<div class="form-group"><label class="col-sm-3 control-label">站点名称</label><div class="col-sm-6"><input type="text" name="Name" class="form-control" value="{{ site.Name }}"></div></div>
<div class="form-group"><label class="col-sm-3 control-label">烟雾检测conf阈值</label><div class="col-sm-6"><input type="number" step="0.01" name="thresh" class="form-control" value="{{ site.thresh }}"><span class="help-block">阈值越高越不容易报警，阈值越低越容易报警</span></div></div>
<div class="form-group"><label class="col-sm-3 control-label">图片/视频长</label><div class="col-sm-6"><input type="number" name="width" class="form-control" value="{{ site.width }}"></div></div>
<div class="form-group"><label class="col-sm-3 control-label">图片/视频宽</label><div class="col-sm-6"><input type="number" name="height" class="form-control" value="{{ site.height }}"></div></div>
<div class="form-group"><label class="col-sm-3 control-label">视频秒数</label><div class="col-sm-6"><input type="number" name="video_times" class="form-control" value="{{ site.video_times }}"></div></div>
<div class="form-group"><label class="col-sm-3 control-label">连接心跳时间(小时)</label><div class="col-sm-6"><input type="number" name="heartBeat" class="form-control" value="{{ site.heartBeat }}"></div></div>
<div class="form-group"><label class="col-sm-3 control-label">网络异常误差(分钟)</label><div class="col-sm-6"><input type="number" name="exception_times" class="form-control" value="{{ site.exception_times }}"></div></div>
<div class="form-group"><div class="col-sm-offset-3 col-sm-6"><button type="submit" class="btn btn-primary">保存配置</button></div></div>
</form></div></div></div></body></html>
"""

BRANCH_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>部门管理</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}.panel{border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}</style></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>部门管理</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增部门</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>部门名称</th><th>上级部门</th><th>备注</th><th>操作</th></tr></thead>
<tbody>{% for b in branches %}<tr><td>{{ b.Id }}</td><td>{{ b.Name }}</td><td>{{ b.ParentId }}</td><td>{{ b.Remark or '' }}</td>
<td><button class="btn btn-xs btn-warning" onclick="editBranch({{ b.Id }},'{{ b.Name }}',{{ b.ParentId }},'{{ b.Remark or '' }}')">修改</button>
<a href="/admin/branch/delete/{{ b.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/branch/add"><div class="modal-header"><h4>新增部门</h4></div>
<div class="modal-body"><div class="form-group"><label>部门名称</label><input type="text" name="Name" class="form-control" required></div>
<div class="form-group"><label>上级部门ID</label><input type="number" name="ParentId" class="form-control" value="0"></div>
<div class="form-group"><label>备注</label><textarea name="Remark" class="form-control" rows="2"></textarea></div></div>
<div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<div class="modal fade" id="editModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" id="editForm"><div class="modal-header"><h4>修改部门</h4></div>
<div class="modal-body"><div class="form-group"><label>部门名称</label><input type="text" name="Name" id="eName" class="form-control" required></div>
<div class="form-group"><label>上级部门ID</label><input type="number" name="ParentId" id="eParent" class="form-control"></div>
<div class="form-group"><label>备注</label><textarea name="Remark" id="eRemark" class="form-control" rows="2"></textarea></div></div>
<div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<script>function editBranch(id,name,parent,remark){document.getElementById('editForm').action='/admin/branch/edit/'+id;document.getElementById('eName').value=name;document.getElementById('eParent').value=parent;document.getElementById('eRemark').value=remark;$('#editModal').modal('show');}</script>
</div></body></html>
"""

USER_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>用户管理</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}.panel{border-radius:8px;}</style></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>用户管理</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增用户</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>账号</th><th>姓名</th><th>部门</th><th>区域</th><th>角色</th><th>操作</th></tr></thead>
<tbody>{% for u in users %}<tr><td>{{ u.Id }}</td><td>{{ u.Account }}</td><td>{{ u.Name }}</td><td>{{ u.BranchName or '' }}</td><td>{{ u.AreaName or '' }}</td><td>{{ u.RoleName or '' }}</td>
<td><button class="btn btn-xs btn-warning" onclick="editUser({{ u.Id }},'{{ u.Account }}','{{ u.Name }}',{{ u.AreaId or 1 }},{{ u.BranchId or 1 }},{{ u.RoleName }})">修改</button>
<a href="/admin/user/delete/{{ u.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/user/add"><div class="modal-header"><h4>新增用户</h4></div>
<div class="modal-body">
<div class="form-group"><label>账号</label><input type="text" name="Account" class="form-control" required></div>
<div class="form-group"><label>姓名</label><input type="text" name="Name" class="form-control" required></div>
<div class="form-group"><label>密码</label><input type="password" name="Password" class="form-control" required></div>
<div class="form-group"><label>区域</label><select name="AreaId" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>部门</label><select name="BranchId" class="form-control">{% for b in branches %}<option value="{{ b.Id }}">{{ b.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>角色</label><select name="RoleId" class="form-control">{% for r in roles %}<option value="{{ r.Id }}">{{ r.Name }}</option>{% endfor %}</select></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<div class="modal fade" id="editModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" id="editForm"><div class="modal-header"><h4>修改用户</h4></div>
<div class="modal-body">
<div class="form-group"><label>账号</label><input type="text" name="Account" id="eAcc" class="form-control" required></div>
<div class="form-group"><label>姓名</label><input type="text" name="Name" id="eName" class="form-control" required></div>
<div class="form-group"><label>新密码(留空不修改)</label><input type="password" name="Password" class="form-control"></div>
<div class="form-group"><label>区域</label><select name="AreaId" id="eArea" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>部门</label><select name="BranchId" id="eBranch" class="form-control">{% for b in branches %}<option value="{{ b.Id }}">{{ b.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>角色</label><select name="RoleId" id="eRole" class="form-control">{% for r in roles %}<option value="{{ r.Id }}">{{ r.Name }}</option>{% endfor %}</select></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<script>function editUser(id,acc,name,area,branch,roleName){document.getElementById('editForm').action='/admin/user/edit/'+id;document.getElementById('eAcc').value=acc;document.getElementById('eName').value=name;document.getElementById('eArea').value=area;document.getElementById('eBranch').value=branch;Array.from(document.getElementById('eRole').options).forEach(function(o){o.selected=o.text===roleName;});$('#editModal').modal('show');}</script>
</div></body></html>
"""

ROLE_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>角色管理</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}</style></head><body><div class="container-fluid" style="margin-top:60px;">
<h3>角色管理</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增角色</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>角色名</th><th>描述</th><th>操作</th></tr></thead>
<tbody>{% for r in roles %}<tr><td>{{ r.Id }}</td><td>{{ r.Name }}</td><td>{{ r.Description or '' }}</td>
<td><a href="/admin/role/delete/{{ r.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>

<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/role/add"><div class="modal-header"><h4>新增角色</h4></div>
<div class="modal-body"><div class="form-group"><label>角色名</label><input type="text" name="Name" class="form-control" required></div>
<div class="form-group"><label>描述</label><textarea name="Description" class="form-control" rows="2"></textarea></div>
<div class="form-group"><label>权限</label><br>
{% set all_auths = ['system_config','department','user','role','device','camera','alarm','audit','log','dashboard','dictionary'] %}
{% set auth_names = {'system_config':'系统配置','department':'部门管理','user':'用户管理','role':'角色管理','device':'AI分析盒','camera':'摄像头','alarm':'报警事件','audit':'事件审核','log':'日志管理','dashboard':'数据大屏','dictionary':'数据字典'} %}
{% for a in all_auths %}<label class="checkbox-inline"><input type="checkbox" name="authorities" value="{{ a }}"> {{ auth_names.get(a, a) }}</label>{% endfor %}
</div></div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
</div></body></html>
"""

DICT_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>数据字典</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}</style></head><body><div class="container-fluid" style="margin-top:60px;">
<h3>数据字典</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增字典项</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>Key</th><th>Value</th><th>备注</th><th>操作</th></tr></thead>
<tbody>{% for it in items %}<tr><td>{{ it.Id }}</td><td>{{ it.Key }}</td><td>{{ it.Value }}</td><td>{{ it.Remark or '' }}</td>
<td><a href="/admin/dictionary/delete/{{ it.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/dictionary/add"><div class="modal-header"><h4>新增字典项</h4></div>
<div class="modal-body"><div class="form-group"><label>Key</label><input type="text" name="Key" class="form-control" required></div>
<div class="form-group"><label>Value</label><input type="text" name="Value" class="form-control" required></div>
<div class="form-group"><label>备注</label><input type="text" name="Remark" class="form-control"></div></div>
<div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
</div></body></html>
"""

DEVICE_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>AI分析盒管理</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}</style></head><body><div class="container-fluid" style="margin-top:60px;">
<h3>AI分析盒管理</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增AI分析盒</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>MAC</th><th>位置</th><th>区域</th><th>模型</th><th>最后通信</th><th>操作</th></tr></thead>
<tbody>{% for d in devices %}<tr><td>{{ d.Id }}</td><td>{{ d.MAC }}</td><td>{{ d.Address or '' }}</td><td>{{ d.AreaName or '' }}</td><td>{{ d.ModelInfo or '' }}</td><td>{{ d.LastConnectTime or '-' }}</td>
<td><button class="btn btn-xs btn-warning" onclick="editDevice({{ d.Id }},'{{ d.MAC or '' }}','{{ d.Longitude or '' }}','{{ d.Latitude or '' }}','{{ d.Address or '' }}',{{ d.AreaId or 1 }},'{{ d.ModelInfo or '' }}')">修改</button>
<a href="/admin/device/delete/{{ d.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/device/add"><div class="modal-header"><h4>新增AI分析盒</h4></div>
<div class="modal-body">
<div class="form-group"><label>MAC地址</label><input type="text" name="MAC" class="form-control"></div>
<div class="form-group"><label>经度</label><input type="text" name="Longitude" class="form-control"></div>
<div class="form-group"><label>纬度</label><input type="text" name="Latitude" class="form-control"></div>
<div class="form-group"><label>位置</label><input type="text" name="Address" class="form-control"></div>
<div class="form-group"><label>区域</label><select name="AreaId" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>模型信息</label><input type="text" name="ModelInfo" class="form-control" value="YOLOv11-Fire"></div>
<div class="form-group"><label>维护人</label><input type="text" name="Maintainer" class="form-control"></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<div class="modal fade" id="editModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" id="editForm"><div class="modal-header"><h4>修改AI分析盒</h4></div>
<div class="modal-body">
<div class="form-group"><label>MAC地址</label><input type="text" name="MAC" id="eMAC" class="form-control"></div>
<div class="form-group"><label>经度</label><input type="text" name="Longitude" id="eLng" class="form-control"></div>
<div class="form-group"><label>纬度</label><input type="text" name="Latitude" id="eLat" class="form-control"></div>
<div class="form-group"><label>位置</label><input type="text" name="Address" id="eAddr" class="form-control"></div>
<div class="form-group"><label>区域</label><select name="AreaId" id="eArea" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>模型信息</label><input type="text" name="ModelInfo" id="eModel" class="form-control"></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<script>function editDevice(id,mac,lng,lat,addr,area,model){document.getElementById('editForm').action='/admin/device/edit/'+id;document.getElementById('eMAC').value=mac;document.getElementById('eLng').value=lng;document.getElementById('eLat').value=lat;document.getElementById('eAddr').value=addr;document.getElementById('eArea').value=area;document.getElementById('eModel').value=model;$('#editModal').modal('show');}</script>
</div></body></html>
"""

CAMERA_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>摄像头管理</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}</style></head><body><div class="container-fluid" style="margin-top:60px;">
<h3>摄像头管理</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<button class="btn btn-primary" data-toggle="modal" data-target="#addModal">新增摄像头</button>
<table class="table table-striped table-hover" style="margin-top:15px;background:white;">
<thead><tr><th>ID</th><th>名称</th><th>IP</th><th>MAC</th><th>区域</th><th>型号</th><th>关联AI盒</th><th>操作</th></tr></thead>
<tbody>{% for c in cameras %}<tr><td>{{ c.Id }}</td><td>{{ c.Name }}</td><td>{{ c.IP }}</td><td>{{ c.MAC }}</td><td>{{ c.AreaName or '' }}</td><td>{{ c.Type }}</td><td>{{ c.DeviceMAC or '' }}</td>
<td><button class="btn btn-xs btn-warning" onclick="editCam({{ c.Id }},'{{ c.IP or '' }}','{{ c.MAC or '' }}','{{ c.CameraUrl or '' }}','{{ c.Name or '' }}','{{ c.Longitude or '' }}','{{ c.Latitude or '' }}',{{ c.AreaId or 1 }},'{{ c.Type or '' }}',{{ c.DeviceId or 1 }})">修改</button>
<a href="/admin/camera/delete/{{ c.Id }}" class="btn btn-xs btn-danger" onclick="return confirm('确认删除?')">删除</a></td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" action="/admin/camera/add"><div class="modal-header"><h4>新增摄像头</h4></div>
<div class="modal-body">
<div class="form-group"><label>名称</label><input type="text" name="Name" class="form-control" required></div>
<div class="form-group"><label>IP地址</label><input type="text" name="IP" class="form-control"></div>
<div class="form-group"><label>MAC地址</label><input type="text" name="MAC" class="form-control"></div>
<div class="form-group"><label>摄像头URL</label><input type="text" name="CameraUrl" class="form-control"></div>
<div class="form-group"><label>经度</label><input type="text" name="Longitude" class="form-control"></div>
<div class="form-group"><label>纬度</label><input type="text" name="Latitude" class="form-control"></div>
<div class="form-group"><label>区域</label><select name="AreaId" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>型号</label><select name="Type" class="form-control"><option>海康威视</option><option>大华</option><option>宇视</option><option>其他</option></select></div>
<div class="form-group"><label>关联AI分析盒</label><select name="DeviceId" class="form-control">{% for d in devices %}<option value="{{ d.Id }}">{{ d.MAC }} - {{ d.Address or 'N/A' }}</option>{% endfor %}</select></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<div class="modal fade" id="editModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" id="editForm"><div class="modal-header"><h4>修改摄像头</h4></div>
<div class="modal-body">
<div class="form-group"><label>名称</label><input type="text" name="Name" id="eName" class="form-control" required></div>
<div class="form-group"><label>IP地址</label><input type="text" name="IP" id="eIP" class="form-control"></div>
<div class="form-group"><label>MAC地址</label><input type="text" name="MAC" id="eMAC" class="form-control"></div>
<div class="form-group"><label>摄像头URL</label><input type="text" name="CameraUrl" id="eUrl" class="form-control"></div>
<div class="form-group"><label>经度</label><input type="text" name="Longitude" id="eLng" class="form-control"></div>
<div class="form-group"><label>纬度</label><input type="text" name="Latitude" id="eLat" class="form-control"></div>
<div class="form-group"><label>区域</label><select name="AreaId" id="eArea" class="form-control">{% for a in areas %}<option value="{{ a.Id }}">{{ a.Name }}</option>{% endfor %}</select></div>
<div class="form-group"><label>型号</label><select name="Type" id="eType" class="form-control"><option>海康威视</option><option>大华</option><option>宇视</option><option>其他</option></select></div>
<div class="form-group"><label>关联AI分析盒</label><select name="DeviceId" id="eDevice" class="form-control">{% for d in devices %}<option value="{{ d.Id }}">{{ d.MAC }} - {{ d.Address or 'N/A' }}</option>{% endfor %}</select></div>
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<script>function editCam(id,ip,mac,url,name,lng,lat,area,type,did){document.getElementById('editForm').action='/admin/camera/edit/'+id;document.getElementById('eName').value=name;document.getElementById('eIP').value=ip;document.getElementById('eMAC').value=mac;document.getElementById('eUrl').value=url;document.getElementById('eLng').value=lng;document.getElementById('eLat').value=lat;document.getElementById('eArea').value=area;document.getElementById('eType').value=type;document.getElementById('eDevice').value=did;$('#editModal').modal('show');}</script>
</div></body></html>
"""

ALARM_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>报警事件</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;} .alarm-img{max-width:120px;max-height:80px;cursor:pointer;}</style></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>报警事件</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>图片</th><th>位置</th><th>经度</th><th>纬度</th><th>摄像头</th><th>时间</th><th>状态</th><th>处理人</th><th>操作</th></tr></thead>
<tbody>{% for a in alarms %}<tr>
<td>{{ a.Id }}</td><td>{% if a.Picture %}<img src="{{ a.Picture }}" class="alarm-img" onclick="window.open('{{ a.Picture }}')">{% else %}-{% endif %}</td>
<td>{{ a.Location or '-' }}</td><td>{{ a.Longitude }}</td><td>{{ a.Latitude }}</td>
<td>{{ a.CameraName or '-' }}</td><td>{{ a.CreatTime }}</td>
<td>{% if a.Status=='1' %}<span class="label label-danger">报警</span>{% elif a.Status=='2' %}<span class="label label-warning">待审核</span>{% elif a.Status=='3' %}<span class="label label-success">已审核</span>{% endif %}</td>
<td>{{ a.OperatorName or '-' }}</td>
<td>
{% if a.VideoUrl %}<a href="{{ a.VideoUrl }}" target="_blank" class="btn btn-xs btn-info">视频</a>{% endif %}
{% if a.Status=='1' %}<button class="btn btn-xs btn-warning" onclick="$('#aid').val({{ a.Id }});$('#processModal').modal('show')">处理</button>{% endif %}
</td></tr>{% endfor %}</tbody></table>
<div class="modal fade" id="processModal"><div class="modal-dialog"><div class="modal-content">
<form method="post" id="processForm"><div class="modal-header"><h4>处理报警事件</h4></div>
<div class="modal-body"><input type="hidden" id="aid">
<div class="form-group"><label>事件紧急程度</label><select name="UrgencyDegree" class="form-control"><option>一般</option><option>紧急</option><option>非常紧急</option></select></div>
<div class="form-group"><label>处理结果</label><select name="OperateResult" class="form-control"><option>已处理</option><option>误报</option><option>待观察</option><option>无需处理</option></select></div>
<div class="form-group"><label>事件描述</label><textarea name="Description" class="form-control" rows="3"></textarea></div></div>
<div class="modal-footer"><button type="submit" class="btn btn-primary">提交处理</button><button type="button" class="btn btn-default" data-dismiss="modal">取消</button></div></form></div></div></div>
<script>$('#processModal').on('show.bs.modal',function(){var aid=$('#aid').val();$('#processForm').attr('action','/admin/alarm/process/'+aid);});</script>
</div></body></html>
"""

AUDIT_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>事件处理审核</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
<script src="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js"></script>
<style>body{background:#f0f2f5;}</style></head><body><div class="container-fluid" style="margin-top:60px;">
<h3>事件处理审核</h3>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="alert alert-success">{{ msgs[0] }}</div>{% endif %}{% endwith %}
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>位置</th><th>摄像头</th><th>报警时间</th><th>处理人</th><th>处理结果</th><th>处理时间</th><th>操作</th></tr></thead>
<tbody>{% for a in alarms %}<tr>
<td>{{ a.Id }}</td><td>{{ a.Location or '-' }}</td><td>{{ a.CameraName or '-' }}</td><td>{{ a.CreatTime }}</td><td>{{ a.OperatorName or '-' }}</td>
<td>{{ a.OperateResult or '-' }}</td><td>{{ a.OperateTime or '-' }}</td>
<td><a href="/admin/audit/approve/{{ a.Id }}" class="btn btn-xs btn-success">通过</a>
<a href="/admin/audit/reject/{{ a.Id }}" class="btn btn-xs btn-danger">驳回</a></td></tr>{% endfor %}</tbody></table>
</div></body></html>
"""

CAMERA_ERROR_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>摄像头故障</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet"></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>摄像头故障</h3>
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>摄像头</th><th>MAC</th><th>故障时间</th><th>故障码</th><th>详情</th></tr></thead>
<tbody>{% for e in errors %}<tr><td>{{ e.Id }}</td><td>{{ e.CameraName or e.CameraId }}</td><td>{{ e.MAC }}</td><td>{{ e.CreateTime }}</td><td>{{ e.ErrorCode }}</td><td>{{ e.ErrorMsg or '' }}</td></tr>{% endfor %}</tbody></table>
</div></body></html>
"""

DEVICE_ERROR_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>AI分析盒故障</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet"></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>AI分析盒故障</h3>
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>设备ID</th><th>MAC</th><th>故障时间</th><th>故障码</th><th>详情</th></tr></thead>
<tbody>{% for e in errors %}<tr><td>{{ e.Id }}</td><td>{{ e.DeviceAddress or e.DeviceId }}</td><td>{{ e.DeviceMAC or e.MAC }}</td><td>{{ e.CreateTime }}</td><td>{{ e.ErrorCode }}</td><td>{{ e.ErrorMsg or '' }}</td></tr>{% endfor %}</tbody></table>
</div></body></html>
"""

ACCESS_LOG_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>访问日志</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet"></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>访问日志</h3>
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>用户</th><th>登录时间</th><th>IP</th><th>登录方式</th></tr></thead>
<tbody>{% for l in logs %}<tr><td>{{ l.Id }}</td><td>{{ l.UserName or l.UserId }}</td><td>{{ l.LoginTime }}</td><td>{{ l.LoginInIp }}</td><td>{{ l.LoginType }}</td></tr>{% endfor %}</tbody></table>
</div></body></html>
"""

OPERATE_LOG_TEMPLATE = BASE_NAV + """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>操作日志</title>
<link href="https://cdn.bootcdn.net/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" rel="stylesheet"></head>
<body><div class="container-fluid" style="margin-top:60px;">
<h3>操作日志</h3>
<table class="table table-striped table-hover" style="background:white;">
<thead><tr><th>ID</th><th>功能</th><th>操作类型</th><th>内容</th><th>时间</th><th>用户</th></tr></thead>
<tbody>{% for l in logs %}<tr><td>{{ l.Id }}</td><td>{{ l.MenuName }}</td><td>{{ l.Type }}</td><td style="max-width:300px;overflow:hidden;">{{ l.ContentNew }}</td><td>{{ l.CreateTime }}</td><td>{{ l.UserName or l.UserId }}</td></tr>{% endfor %}</tbody></table>
</div></body></html>
"""


if __name__ == "__main__":
    init_db()
    logger.info("Starting Web Management Server...")
    logger.info("访问地址: http://0.0.0.0:5000")
    logger.info("管理员: admin / 123456")
    logger.info("处理人: chuli001 / 123456")
    app.run(host="0.0.0.0", port=5000, debug=True)
