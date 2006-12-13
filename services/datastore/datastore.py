#!/bin/python
# Copyright (C) 2006, Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import dbus, dbus.glib, gobject
import logging
import sqlite
import dbus_helpers

have_sugar = False
try:
    from sugar import env
    have_sugar = True
except ImportError:
    pass


_DS_SERVICE = "org.laptop.sugar.DataStore"
_DS_DBUS_INTERFACE = "org.laptop.sugar.DataStore"
_DS_OBJECT_PATH = "/org/laptop/sugar/DataStore"

_DS_OBJECT_DBUS_INTERFACE = "org.laptop.sugar.DataStore.Object"
_DS_OBJECT_OBJECT_PATH = "/org/laptop/sugar/DataStore/Object"

class NotFoundError(Exception):
    pass

def _create_op(uid):
    return "%s/%d" % (_DS_OBJECT_OBJECT_PATH, uid)

def _get_uid_from_op(op):
    if not op.startswith(_DS_OBJECT_OBJECT_PATH + "/"):
        raise ValueError("Invalid object path %s." % op)
    item = op[len(_DS_OBJECT_OBJECT_PATH + "/"):]
    return int(item)

def _get_data_as_string(data):
    if isinstance(data, list):
        data_str = ""
        for item in data:
            data_str += chr(item)
        return data_str
    elif isinstance(data, int):
        return str(data)
    elif isinstance(data, str):
        return data
    elif isinstance(data, unicode):
        return str(data)
    else:
        raise ValueError("Unsupported data type")

class DataStoreDBusHelper(dbus.service.Object):
    def __init__(self, parent, bus_name):
        self._parent = parent
        self._bus_name = bus_name
        dbus.service.Object.__init__(self, bus_name, _DS_OBJECT_PATH)

    @dbus.service.method(_DS_DBUS_INTERFACE,
                        in_signature="x", out_signature="o")
    def get(self, uid):
        return _create_op(self._parent.get(uid))

    @dbus.service.method(_DS_DBUS_INTERFACE,
                        in_signature="aya{sv}", out_signature="o")
    def create(self, data, prop_dict):
        uid = self._parent.create(data, prop_dict)
        return _create_op(uid)

    @dbus.service.method(_DS_DBUS_INTERFACE,
                        in_signature="o", out_signature="i")
    def delete(self, op):
        uid = _get_uid_from_op(op)
        self._parent.delete(uid)
        return 0

    @dbus.service.method(_DS_DBUS_INTERFACE,
                        in_signature="a{sv}", out_signature="ao")
    def find(self, prop_dict):
        uids = self._parent.find(prop_dict)
        ops = []
        for uid in uids:
            ops.append(_create_op(uid))
        return ops

class ObjectDBusHelper(dbus_helpers.FallbackObject):
    def __init__(self, parent, bus_name):
        self._parent = parent
        self._bus_name = bus_name
        dbus_helpers.FallbackObject.__init__(self, bus_name, _DS_OBJECT_OBJECT_PATH)

    @dbus_helpers.method(_DS_OBJECT_DBUS_INTERFACE,
                         in_signature="", out_signature="ay", dbus_message_keyword="dbus_message")
    def get_data(self, dbus_message=None):
        if not dbus_message:
            raise RuntimeError("Need the dbus message.")
        uid = _get_uid_from_op(dbus_message.get_path())
        return self._parent.get_data(uid)

    @dbus_helpers.method(_DS_OBJECT_DBUS_INTERFACE,
                         in_signature="ay", out_signature="i", dbus_message_keyword="dbus_message")
    def set_data(self, data, dbus_message=None):
        if not dbus_message:
            raise RuntimeError("Need the dbus message.")
        uid = _get_uid_from_op(dbus_message.get_path())
        self._parent.set_data(uid, data)
        return 0

    @dbus_helpers.method(_DS_OBJECT_DBUS_INTERFACE,
                         in_signature="as", out_signature="a{sv}", dbus_message_keyword="dbus_message")
    def get_properties(self, keys, dbus_message=None):
        if not dbus_message:
            raise RuntimeError("Need the dbus message.")
        uid = _get_uid_from_op(dbus_message.get_path())
        return self._parent.get_properties(uid, keys)

    @dbus_helpers.method(_DS_OBJECT_DBUS_INTERFACE,
                         in_signature="a{sv}", out_signature="i", dbus_message_keyword="dbus_message")
    def set_properties(self, prop_dict, dbus_message=None):
        if not dbus_message:
            raise RuntimeError("Need the dbus message.")
        uid = _get_uid_from_op(dbus_message.get_path())
        self._parent.set_properties(uid, prop_dict)
        return 0

    @dbus_helpers.fallback_signal(_DS_OBJECT_DBUS_INTERFACE,
                                  signature="ba{sv}b", ignore_args=["uid"])
    def Updated(self, data, prop_dict, deleted, uid=None):
        # Return the object path so the signal decorator knows what
        # object this signal should be fore
        if not uid:
            raise RuntimeError("Need a UID.")
        op = _create_op(uid)
        return op

class DataStore(object):
    def __init__(self):
        self._session_bus = dbus.SessionBus()
        self._bus_name = dbus.service.BusName(_DS_SERVICE, bus=self._session_bus)        
        self._dbus_helper = DataStoreDBusHelper(self, self._bus_name)
        self._dbus_obj_helper = ObjectDBusHelper(self, self._bus_name)

        ppath = "/tmp"
        if have_sugar:
            ppath = env.get_profile_path()
        self._dbfile = os.path.join(ppath, "ds", "data-store.db")
        if not os.path.exists(os.path.dirname(self._dbfile)):
            os.makedirs(os.path.dirname(self._dbfile), 0755)

        self._dbcx = sqlite.connect(self._dbfile, encoding="utf-8", timeout=3)
        try:
            self._ensure_table()
        except StandardError, e:
            logging.info("Could not access the data store.  Reason: '%s'.  Exiting..." % e)
            os._exit(1)

    def __del__(self):
        self._dbcx.close()
        del self._dbcx

    def _ensure_table(self):
        curs = self._dbcx.cursor()
        try:
            curs.execute('SELECT * FROM properties LIMIT 4')
            self._dbcx.commit()
        except Exception, e:
            # If table wasn't created, try to create it
            self._dbcx.commit()
            curs.execute('CREATE TABLE objects (' \
                'uid INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, ' \
                'data BLOB' \
                ');')
            curs.execute('CREATE TABLE properties (' \
                'objid INTEGER NOT NULL, '           \
                'key VARCHAR(100),'                  \
                'value VARCHAR(200)'                 \
                ');')
            curs.execute('CREATE INDEX objid_idx ON properties(objid);')
            self._dbcx.commit()
        del curs

    def get(self, uid):
        curs = self._dbcx.cursor()
        curs.execute('SELECT uid FROM objects WHERE uid=%d;' % uid)
        res = curs.fetchall()
        self._dbcx.commit()
        del curs
        if len(res) > 0:
            return uid
        raise NotFoundError("Object %d was not found." % uid)

    def create(self, data, prop_dict=None):
        curs = self._dbcx.cursor()
        data = sqlite.encode(_get_data_as_string(data))
        curs.execute("INSERT INTO objects (uid, data) VALUES (NULL, '%s');" % data)
        curs.execute("SELECT last_insert_rowid();")
        rows = curs.fetchall()
        self._dbcx.commit()
        last_row = rows[0]
        uid = last_row[0]
        for (key, value) in prop_dict.items():
            safe_key = key.replace("'", "''")
            value = sqlite.encode(_get_data_as_string(value))
            curs.execute("INSERT INTO properties (objid, key, value) VALUES (%d, '%s', '%s');" % (uid, safe_key, value))
        self._dbcx.commit()
        del curs
        return uid

    def delete(self, uid):
        curs = self._dbcx.cursor()
        curs.execute("DELETE FROM objects WHERE (uid=%d);" % uid)
        curs.execute("DELETE FROM properties WHERE (objid=%d);" % uid)
        self._dbcx.commit()
        del curs
        self._dbus_obj_helper.Updated(False, {}, True, uid=uid)
        return 0

    def find(self, prop_dict):
        query = "SELECT objid FROM properties"
        subquery = ""
        for (key, value) in prop_dict.items():
            safe_key = key.replace("'", "''")
            value = _get_data_as_string(value)
            if not len(value):
                raise ValueError("Property values must not be blank.")
            substr = "(key='%s' AND value='%s')" % (safe_key, sqlite.encode(value))
            if len(subquery) > 0:
                subquery += " OR "
            subquery += substr
        if len(subquery):
            query += " WHERE (%s)" % subquery
        query += ";"
        curs = self._dbcx.cursor()
        curs.execute(query)
        rows = curs.fetchall()
        self._dbcx.commit()
        # FIXME: ensure that each properties.objid has a match in objects.uid
        uids = []
        for row in rows:
            uids.append(row['objid'])
        del curs
        return uids

    def set_data(self, uid, data):
        curs = self._dbcx.cursor()
        curs.execute('SELECT uid FROM objects WHERE uid=%d;' % uid)
        res = curs.fetchall()
        self._dbcx.commit()
        if len(res) <= 0:
            del curs
            raise NotFoundError("Object %d was not found." % uid)
        data = sqlite.encode(_get_data_as_string(data))
        curs.execute("UPDATE objects SET data='%s' WHERE uid=%d;" % (data, uid))
        self._dbcx.commit()
        del curs
        self._dbus_obj_helper.Updated(True, {}, False, uid=uid)

    _reserved_keys = ["uid", "objid", "data", "created", "modified"]
    def set_properties(self, uid, prop_dict):
        curs = self._dbcx.cursor()
        curs.execute('SELECT uid FROM objects WHERE uid=%d;' % uid)
        res = curs.fetchall()
        self._dbcx.commit()
        if len(res) <= 0:
            del curs
            raise NotFoundError("Object %d was not found." % uid)

        for key in prop_dict.keys():
            if key in self._reserved_keys:
                raise ValueError("key %s is a reserved key." % key)

        for (key, value) in prop_dict.items():
            safe_key = key.replace("'", "''")
            value = _get_data_as_string(value)
            if not len(value):
                # delete the property
                curs.execute("DELETE FROM properties WHERE (objid=%d AND key='%s');" % (uid, safe_key))
            else:
                enc_value = sqlite.encode(value)
                curs.execute("SELECT objid FROM properties WHERE (objid=%d AND key='%s');" % (uid, safe_key))
                if len(curs.fetchall()) > 0:
                    curs.execute("UPDATE properties SET value='%s' WHERE (objid=%d AND key='%s');" % (enc_value, uid, safe_key))
                else:
                    curs.execute("INSERT INTO properties (objid, key, value) VALUES (%d, '%s', '%s');" % (uid, safe_key, enc_value))
        self._dbcx.commit()
        del curs
        self._dbus_obj_helper.Updated(False, {}, False, uid=uid)

    def get_data(self, uid):
        curs = self._dbcx.cursor()
        curs.execute('SELECT uid, data FROM objects WHERE uid=%d;' % uid)
        res = curs.fetchall()
        self._dbcx.commit()
        if len(res) <= 0:
            raise NotFoundError("Object %d was not found." % uid)
        data = res[0][1]
        del curs
        return data

    def get_properties(self, uid, keys):
        query = "SELECT objid, key, value FROM properties WHERE (objid=%d" % uid
        subquery = ""
        if len(keys) > 0:
            for key in keys:
                if len(subquery) > 0:
                    subquery += " OR "
                safe_key = key.replace("'", "''")
                subquery += "key='%s'" % safe_key
            subquery += ")"
        query += subquery + ");"
        curs = self._dbcx.cursor()
        curs.execute(query)
        rows = curs.fetchall()
        self._dbcx.commit()
        prop_dict = {}
        for row in rows:
            conv_key = row['key'].replace("''", "'")
            prop_dict[conv_key] = sqlite.decode(row['value'])
        prop_dict['uid'] = str(uid)
        del curs
        return prop_dict


def main():
    loop = gobject.MainLoop()
    ds = DataStore()
    try:
        loop.run()
    except KeyboardInterrupt:
        print 'Ctrl+C pressed, exiting...'

if __name__ == "__main__":
    main()