import hashlib
import json
from struct import pack, unpack, calcsize
from gzip import GzipFile

read_and_unpack = lambda f, o: unpack(f, o.read(calcsize(f)))

def filename_id(filename):
     id_hash = hashlib.md5(filename).hexdigest()
     return "%s-%s-%s-%s-%s"%(id_hash[0:8], id_hash[8:12], id_hash[12:16], id_hash[16:20], id_hash[20:])

def singleton(cls):
    instance_container = []
    def getinstance():
        if not len(instance_container):
            instance_container.append(cls())
        return instance_container[0]
    return getinstance

#def get_name(cls):
#    import inspect
#    return '.'.join(reversed([kls.__name__ for kls in inspect.getmro(cls)][:-1]))

def print_and_return(obj, ident):
    #if DEBUG:
    #print " "*2*ident + "%s" % obj
    return obj

class AVEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'name') and hasattr(obj, "data"):
            return ("AVObject: %s" % obj.name, obj.data)
        if hasattr(obj, 'read'):
            pos = obj.tell()
            obj.seek(0, 2)
            size = obj.tell()
            obj.seek(0)
            return "<Data size:%s>" % size
        return json.JSONEncoder.default(self, obj)

def pprint(obj, level=1):
    import json
    print json.dumps(obj, cls=AVEncoder, indent=4)

def pprint2(obj, level=1):
    from pprint import pformat
    indent = " "*level*4
    if isinstance(obj, dict):
        data = []
        for key, value in obj.iteritems():
            if isinstance(value, list) or isinstance(value, dict):
                value_repr = pprint(value, level+1)
            elif isinstance(value, basestring):
                value_repr = "'%s'" % value
            else:
                value_repr = "%s" % value
            data.append(indent+"%s: %s" % (key, value_repr))
        if hasattr(obj, "name"):
            value = "<dict '%s' {\n%s\n%s}>" % (obj.name, ('\n').join(data), " "*(level-1)*4)
        else:
            value = "<dict {\n%s\n%s}>" % (('\n').join(data), " "*(level-1)*4)
    elif isinstance(obj, list):
        data = []
        for value in obj:
            if isinstance(value, list) or isinstance(value, dict):
                value_repr = pprint(value, level+1)
            elif isinstance(value, basestring):
                value_repr = "'%s'" % value
            else:
                value_repr = "%s" % value
            data.append(indent+"%s" % (value_repr))
        value = "[\n%s\n%s]" % (('\n').join(data), " "*(level-1)*4)
    elif isinstance(obj, basestring):
        return "'%s'" % obj
    else:
        return "%s" % obj
        
    if level == 1:
        print value
    else:
        return value
