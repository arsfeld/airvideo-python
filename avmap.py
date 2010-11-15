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
        return "<AVDict, name: %s, items: '%s'>" % (self.name, 
            ','.join([('%s: %s' % (k, v)) for k, v in self.iteritems()]))
        
read_and_unpack = lambda f, o: unpack(f, o.read(calcsize(f)))

def join(*args):
    return ''.join(args)

def get_name(cls):
    import inspect
    return '.'.join(reversed([kls.__name__ for kls in inspect.getmro(cls)][:-1]))

def from_avmap(stream):
    if isinstance(stream, basestring):
        stream = StringIO.StringIO(stream)
    id_ = read_and_unpack("c", stream)[0]
    if id_ == "a":
        c, n = read_and_unpack("!LL", stream)
        return [from_avmap(stream) for i in range(n)]
    elif id_ == "o":
        c, name_length = read_and_unpack("!LL", stream)
        name = stream.read(name_length)
        version, n = read_and_unpack("!LL", stream)
        values = {}
        for i in range(n):
            key_length = read_and_unpack("!L", stream)[0]
            key = stream.read(key_length)
            values[key] = from_avmap(stream)
        return AVDict(name, values)
    elif id_ == "x":
        c, length = read_and_unpack("!LL", stream)
        return StringIO.StringIO(stream.read(length))
    elif id_ == "s":
        c, length = read_and_unpack("!LL", stream)
        return str(stream.read(length))
    elif id_ == "n":
        return None
    elif id_ == "i":
        return read_and_unpack("!L", stream)[0]
    elif id_ == "f":
        return read_and_unpack("!f", stream)[0]
    else:
        raise Exception("Invalid id: %s" % id_)

def to_avmap(obj, counter = 0):
    if isinstance(obj, list):
        #letter = (self.is_a? AirVideo::AvMap::BitrateList) ? "e" : "a"
        data = join(*[to_avmap(v) for v in obj])
        return join(pack("!cLL", 'a', counter, len(obj)), data)
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
        return pack("!cf", 'f', obj)
    else:
        d = AVDict(get_name(obj.__class__))
        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            v = getattr(obj, attr)
            if callable(v):
                continue
            d[attr] = v
        return to_avmap(d)

if __name__ == "__main__":
    class B(object):
        pass
    class A(B):
        items = [{'Teste':1}]

    test_avmap = lambda obj: from_avmap(to_avmap(obj)) == obj
    assert test_avmap(None)
    assert test_avmap(1)
    assert test_avmap("A string")
    assert test_avmap([1, 2, 3])
    to_avmap(A())
    
    #obj = AVDict("Teste", {"v1":1,"v3":[1, 2, 3, "Teste", [4, 5], AVDict("Teste2", {"1":3})]})
