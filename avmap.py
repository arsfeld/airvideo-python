import os
from struct import pack, unpack, calcsize
from shutil import copyfileobj
from UserDict import UserDict
import struct

try:
    import cStringIO as StringIO
except:
    import StringIO
    
from utils import print_and_return, pprint, read_and_unpack

class AVDict(UserDict):
    '''Dict with a name.
    
    You need to use this instead of a regular dict to be able to serialize into 
    an avmap. You probably want to use AVObject instead.
    '''

    def __init__(self, name, data = {}):
        UserDict.__init__(self, data)
        self.name = name
        
    def __str__(self):
        return "<AVDict, name: %s, items: {%s}>" % (self.name, 
            ', '.join([('%s: %s' % (k, v)) for k, v in self.data.iteritems()]))
        #return self.__pprint__()
    
    def __repr__(self):
        return self.__str__()
        
def avdict(obj, name = None):
    '''Converts an object into an AVDict'''
    # Get the name from the namespace if available
    if name == None and hasattr(obj, "__namespace__"):
        name = '.'.join([obj.__namespace__, type(obj).__name__])
    elif name == None:
        name = type(obj).__name__
    # An object is simply a dict full with it's attributes set to each
    # attribute of the object
    d = AVDict(name)
    for attr in dir(obj):
        # Do not include hidden attributes
        if attr.startswith("_"):
            continue
        v = getattr(obj, attr)
        # Do not include functions
        if callable(v):
            continue
        # Strip leading underscore (so we can use reserved words as 
        # attributes)
        if attr.endswith("_"):
            attr = attr[:-1]
        d[attr] = v
    return d
        
class AVObject(object):
    '''Object that is able to serialize into an avmap.
    
    The serialization is a convertion to an AVDict first, then serializing the
    dict. The namespace with the class name is used as the dict name.
    '''    
    
    __namespace__="air.video"
    
    def __init__(self, **kwargs):
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
        
    def __str__(self):
        return str(avdict(self))
        
    def __repr__(self):
        return repr(avdict(self))

def loads(string):
    return load(StringIO.StringIO(string))

def load(stream):
    return _load(stream)

def _load(stream, ident=0):
    id_ = read_and_unpack("c", stream)[0]
    d = lambda data, s=ident: print_and_return(data, s)
    if id_ == "a" or id_ == "e" or id_ == "d":
        d("List [")
        c, n = read_and_unpack("!LL", stream)
        items = [_load(stream, ident+1) for i in range(n)]
        d("]")
        return items
    elif id_ == "o":
        c, name_length = read_and_unpack("!LL", stream)
        name = stream.read(name_length)
        version, n = read_and_unpack("!LL", stream)
        values = {}
        d("Dict (%s) {" % name)
        for i in range(n):
            key_length = read_and_unpack("!L", stream)[0]            
            key = stream.read(key_length)
            d("%s:" % key, ident+1)
            values[key] = _load(stream, ident+2)
        d("}")
        return AVDict(name, values)
    elif id_ == "x":
        c, length = read_and_unpack("!LL", stream)
        d('<data, size: %s>' % length)
        
        #import tempfile
        #f = tempfile.NamedTemporaryFile(delete=False)
        #print "Saving to %s" % f.name
        #f.write(stream.read(length))
        #f.close()
        
        return StringIO.StringIO(stream.read(length))
    elif id_ == "s":
        c, length = read_and_unpack("!LL", stream)
        return d(str(stream.read(length)))
    elif id_ == "n":
        return d(None)
    elif id_ == "i" or id_ == "r":
        return d(read_and_unpack("!L", stream)[0])
    elif id_ == "l":
        return d(read_and_unpack("!q", stream)[0])
    elif id_ == "f":
        return d(read_and_unpack("!d", stream)[0])
    else:
        raise Exception("Invalid id: %s" % id_)

def dumps(obj):
    '''Dump an object as a serialized avmap into a string'''
    fp = StringIO.StringIO()
    dump(obj, fp)
    return fp.getvalue()

def dump(obj, fp):
    '''Dump an object as a serialized avmap into a file object'''
    return _dump(obj, fp)

def _dump(obj, fp, counter = 0):
    '''Dump an object as a serialized avmap'''
    if isinstance(obj, list):
        #letter = (self.is_a? AirVideo::AvMap::BitrateList) ? "e" : "a"
        fp.write(pack("!cLL", 'a', counter, len(obj)))
        for value in obj:
            _dump(value, fp)
    elif isinstance(obj, bool):
        _dump(int(obj), fp)
    elif isinstance(obj, AVDict):
        #if name == "air.video.ConversionRequest": version = 221
        version = 1
        fp.writelines([pack("!cLL", 'o', counter, len(obj.name)),
                       obj.name,
                       pack("!LL", version, len(obj))])
        for key, value in obj.items():
            key = str(key)
            fp.writelines([pack("!L", len(key)), key])
            _dump(value, fp, counter + 1) 
    elif hasattr(obj, 'read'):
        # Find the size of the obj
        pos = obj.tell()
        obj.seek(0, os.SEEK_END)
        length = obj.tell()
        obj.seek(pos)
        fp.write(pack("!cLL", 'x', counter, length))
        copyfileobj(obj, fp)
        obj.seek(pos)
    elif isinstance(obj, basestring):
        fp.write(pack("!cLL", 's', counter, len(obj)))
        fp.write(obj)
    elif obj is None:
        fp.write(pack("c", 'n'))
    elif isinstance(obj, int):
        fp.write(pack("!cL", 'i', obj))
    elif isinstance(obj, float):
        fp.write(pack("!cd", 'f', obj))
    else:
        #If all else fails, try to convert this into a AVDict
        _dump(avdict(obj), fp)

if __name__ == "__main__":

    test_avmap = lambda obj: loads(dumps(obj)) == obj
    assert test_avmap(None)
    assert test_avmap(1)
    assert test_avmap("A string")
    assert test_avmap([1, 2, 3])
    assert test_avmap(AVDict("Test", {"1":2, "Test":2, "Test2":[1, 2, 3]}))
    
    root = "data"
    if os.path.exists(root):
        for n in os.listdir(root):
            print "Reading file: %s" % n
            with open(os.path.join(root, n)) as f:
                pprint(loads(f.read()))
    
    #stream = dumps(['clientVersions'])
    #data = []
    #for i in stream:
    #    if (i > 'a' and i < 'z') or (i > 'A' and i < 'Z'):
    #        data += [i]
    #    else:
    #        data += "\\%x" % struct.unpack("b", i)
    #print ''.join(data)

    
    #obj = AVDict("Teste", {"v1":1,"v3":[1, 2, 3, "Teste", [4, 5], AVDict("Teste2", {"1":3})]})
