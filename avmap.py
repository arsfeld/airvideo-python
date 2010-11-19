import os
from struct import pack, unpack, calcsize

try:
    import cStringIO as StringIO
except:
    import StringIO

class AVDict(dict):
    def __init__(self, name, v = {}):
        self.name = name
        self.update(v)
        
    def __str__(self):
        return "<AVDict, name: %s, items: {%s}>" % (self.name, 
            ', '.join([('%s: %s' % (k, v)) for k, v in self.iteritems()]))
    
    def __repr__(self):
        return self.__str__()
        
class AVObject(object):
    __namespace__="air.video"
    
    def __init__(self, **kwargs):
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def to_avdict(self):
        # An object is simply a dict full with it's attributes set to each
        # attribute of the object
        d = AVDict('.'.join([self.__namespace__, type(self).__name__]))
        for attr in dir(self):
            # Do not include hidden attributes
            if attr.startswith("_"):
                continue
            v = getattr(self, attr)
            # Do not include functions
            if callable(v):
                continue
            # Strip leading underscore (so we can use reserved words as 
            # attributes)
            if attr.endswith("_"):
                attr = attr[:-1]
            d[attr] = v
        return d
        
    def __str__(self):
        return str(self.to_avdict())
        
    def __repr__(self):
        return repr(self.to_avdict())
        
read_and_unpack = lambda f, o: unpack(f, o.read(calcsize(f)))

def join(*args):
    return ''.join(args)

def get_name(cls):
    import inspect
    return '.'.join(reversed([kls.__name__ for kls in inspect.getmro(cls)][:-1]))

def print_and_return(obj, ident, debug):
    if debug:
        print " "*2*ident + "%s" % obj
    return obj

def from_avmap(stream, ident=0, debug=False):
    if isinstance(stream, basestring):
        stream = StringIO.StringIO(stream)
    id_ = read_and_unpack("c", stream)[0]
    d = lambda data, s=ident: print_and_return(data, s, debug)
    if id_ == "a":
        d("List [")
        c, n = read_and_unpack("!LL", stream)
        items = [from_avmap(stream, ident+1, debug) for i in range(n)]
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
            values[key] = from_avmap(stream, ident+2, debug)
        d("}")
        return AVDict(name, values)
    elif id_ == "x":
        c, length = read_and_unpack("!LL", stream)
        d('<data, size: %s>' % length)
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

def to_avmap(obj, counter = 0):
    if isinstance(obj, list):
        #letter = (self.is_a? AirVideo::AvMap::BitrateList) ? "e" : "a"
        data = join(*[to_avmap(v) for v in obj])
        return join(pack("!cLL", 'a', counter, len(obj)), data)
    elif isinstance(obj, bool):
        return (to_avmap(int(obj)))
    elif isinstance(obj, AVDict):
        #if name == "air.video.ConversionRequest": version = 221
        version = 1
        data = join(*[join(pack("!L", len(key)), key, to_avmap(value, counter)) for 
            key, value in obj.iteritems()])
        return join(pack("!cLL", 'o', counter, len(obj.name)), obj.name,
            pack("!LL", version, len(obj)), data)
    elif hasattr(obj, 'read'):
        return pack("!cL", 'x', counter, self.length) + obj.read()
    elif isinstance(obj, basestring):
        return pack("!cLL", 's', counter, len(obj)) + obj
    elif obj is None:
        return pack("c", 'n')
    elif isinstance(obj, int):
        return pack("!cL", 'i', obj)
    elif isinstance(obj, float):
        return pack("!cd", 'f', obj)
    elif hasattr(obj, 'to_avdict'):
        return to_avmap(obj.to_avdict())
    else:
        raise Exception("Invalid object: %s" % obj)

if __name__ == "__main__":
    class B(object):
        pass
    class A(B):
        items = [{'Teste':1}]
        
    root = "data"
    if os.path.exists(root):
        for n in os.listdir(root):
            print n
            with open(os.path.join(root, n)) as f:
                print from_avmap(f.read(), debug=True)

    test_avmap = lambda obj: from_avmap(to_avmap(obj)) == obj
    assert test_avmap(None)
    assert test_avmap(1)
    assert test_avmap("A string")
    assert test_avmap([1, 2, 3])
    to_avmap(A())
    
    #obj = AVDict("Teste", {"v1":1,"v3":[1, 2, 3, "Teste", [4, 5], AVDict("Teste2", {"1":3})]})
