from lxml import etree
import os

########################
###
###   SECTION
###
########################

class Section(object):
    def __init__(self, name, fields=None, attrs=None):
        self.name = name
        self.fields = fields
        self.attrs = attrs
    
    def section(self):
        tree = etree.Element(self.name)
        if self.attrs:
            for key, value in self.attrs.items():
                tree.set(unicode(key), unicode(value))
                
        if self.fields:
            for field in self.fields:
                tree.append(field.section())
        
        return tree

########################
###
###   XML
###
########################

class Xml(object):
    def __init__(self, path=None, default=None, xpath=None):
        self.path = path
        self._tree = None
        self.default = default
        self.Xpath = xpath

    def clear(self):
        File = open(self.path, 'w')
        File.close()
        
    def save(self):
        File = open(self.path, 'w')
        self.indent(self.tree)
        File.write(etree.tostring(self.tree))
        File.close()
        
    def readFile(self):
        if os.path.exists(self.path):
            try:
                self._tree = etree.parse(open(self.path, 'r')).getroot()
            except:
                self._tree = None
        
        if self._tree is None:
            try:
                os.makedirs(os.sep.join(self.path.split(os.sep)[:-1]))
            except OSError:
                pass
                
            self._tree = etree.Element("all")
            
            if self.default:
                self._tree.append(self.default.section())
                
            self.save()
            
    ########################
    ###   GENERATION & RESTORATION
    ########################
    
    def getXml(self, everything, count, xml, new=None):
        """Used to find an xml file for generation or restoration"""
        if xml is not None:
            return xml
        else:
            xml = None
            if any(item for item in everything):
                o = everything[0]
                xml = o.infoXml()
            else:
                if new:
                    next = new(count)
                    xml = next.infoXml()
        
        return xml
    
    def generate(self, query, xml=None, allInOne=True, numberedAttr=None, xpath=None, many=False):
        """Used to generate xml for everything in the given query"""
        everything = query.all()
        xml = self.getXml(everything, 0, xml)
        
        if xml is not None:
            if allInOne:
                #Everything is in one xml, it is safe to clear everything if there is too much in it
                if len(xml) > len(everything):
                    xml.clear()
            
            count = 1
                
            for item in everything:
                #Make sure xml has correct default
                if hasattr(item, 'xmlStructure'):
                    default = item.xmlStructure
                    if callable(default):
                        xml.default = default()
                    else:
                        xml.default = default
                
                xmlPass = xml
                if xpath and many:
                    xmlPass = xml.xpath(xpath)
                    
                #Make sure we have correct section                
                section = xml.get(count, xmlPass)
                if numberedAttr:
                    section = xml.get(getattr(item, numberedAttr), xmlPass)
                
                #Generate
                item.generate(xml, section)
                count += 1
        
        xml.save()
                
    def restore(self, model, identity, numberedAttr=None, xml=None, finder=None, active=None, 
        zeroBased=False, xpath=None, oneOnly=False, debug=False
    ):
        """Used to restore database objects for all models with the specified identity"""
        
        #######################################################
        # Useful functions
        
        def createNew(count):
            """Function used to create a new model"""
            next = model(**identity)
            if numberedAttr:
                setattr(next, numberedAttr, count)
            return next
        
        def getDiff(first, second):
            """Get's the difference between two numbers whilst taking into account
            whether the numbers are zerobased or not"""
            if zeroBased:
                diff = first - second
            else:
                diff = first + 1 - second
            return diff
        
        def startCount():
            """Creates starting count depending on zero based or not"""
            count = 1
            if zeroBased:
                count = 0
            return count
        
        #######################################################
        # Initialise the query and xml files to be used
        
        query = model.objects.filter(**identity)
        everything = query.all()
        if numberedAttr:
            sortedAll = sorted([(getattr(obj, numberedAttr), obj) for obj in everything])
        else:
            sortedAll = everything
        
        count = startCount()
        
        if finder:
            #finder is used to find all xml files, assuming all objects aren't in the same xml file
            xml = finder()
        xml = self.getXml(everything, count, xml, createNew)
        
        #######################################################
        # Determine if there are objects to be added or deleted
        
        xmlPass = xml
        if xpath:
            xmlPass = xml.xpath(xpath)
        
        if not oneOnly:
            if active:
                objDiff = len([x for x in xmlPass if active(x)]) - len(everything)
            else:
                objDiff = len(xmlPass) - len(everything)
        else:
            objDiff = 0
            if active and not active(xmlPass):
                objDiff = 1
            else:
                if len(everything) == 0:
                    objDiff = 1
        
        #######################################################
        # Add any new objects
            
        if objDiff > 0:
            diff = getDiff(objDiff, count)
            for i in range(diff):
                next = createNew(count+i)
                next.save()
        
        #######################################################
        # create query again incase any objects have been added
        
        query = model.objects.filter(**identity)
        if oneOnly:
            length = 1
        else:
            length = max(len(query), len(xmlPass))
        
        #######################################################
        # Determine how many objects to ultimately restore
        
        countdown = length
        if objDiff < 0:
            countdown = length + objDiff
            
        toDelete = []
        
        #######################################################
        # Restore objects
        def getObjs():
            """Used to get section, item tuples where section refers to part of xml"""
            count = 0
            if not oneOnly:
                for item in xmlPass:
                    if active and active(item) or not active:
                        yield item, query[count]
                        count += 1
                    else:
                        yield item, None
            else:
                yield xmlPass, query[count]
            
            if not oneOnly:
                if count < len(query):
                    for item in query[count:]:
                        yield None, item
                    
        count = startCount()
        for section, item in getObjs():
            if item:
                if countdown <= 0 or section is None:
                    #if we delete them now, it puts the query out of sync
                    toDelete.append(item)
                else:
                    if numberedAttr:
                        setattr(item, numberedAttr, count)
                    
                    item.restore(xml, section)
                    countdown -= 1
            
            #some sections may not be active and thus must be ignored
            count += 1
        
        #######################################################
        # Delete objects
        
        for item in toDelete:
            item.delete()
    
    ########################
    ###   USEFUL
    ########################
    
    def xpath(self, path):
        result = self.tree.xpath(path)
        if result and len(result) == 1:
            return result[0]
        else:
            return result
    
    def indent(self, elem, level=0):
        """Borrowed by http://infix.se/2007/02/06/gentlemen-indent-your-xml"""
        i = "\n" + level*"  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for e in elem:
                self.indent(e, level+1)
                if not e.tail or not e.tail.strip():
                    e.tail = i + "  "
            if not e.tail or not e.tail.strip():
                e.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
    
    ########################
    ###   IO
    ########################
    
        ###   BOOLEANS
        
    def getBool(self, section, attr):
        result = section.get(attr, '')
        if result.lower() in ("yes", "true", 'y'):
            return True
        else:
            return False
    
    def writeBool(self, section, attr, value):
        section.set(attr, unicode(value).lower())

        ###   INTEGERS
    
    def getInt(self, section, attr, default=None):
        result = section.get(attr, default)
        if result.isdigit():
            return int(result)
        else:
            return default
        
    def writeInt(self, section, attr, value):
        section.set(attr, unicode(value))
        
    ########################
    ###   OTHER
    ########################
    
    def __len__(self):
        return len(self.tree)
    
    def __iter__(self):
        for item in self.tree:
            yield item

    def __getattr__(self, key):
        if key == 'tree':
            if self._tree is None:
                self.readFile()
            return self._tree
        
        return object.__getattribute__(self, key)
    
    def __getitem__(self, key):
        """Key assumes 1-based instead of 0-based"""
        return self.getitem(key, self.tree, True)
    
    def getitem(self, key, tree, doSave=False):
        if type(key) is not int:
            try:
                key = int(key)
            except ValueError:
                key = None
        
        if key and key > 0:
            key = key - 1
            diff = len(tree) - key
            if diff < -2:
                raise ValueError("Key is out of range")
            
            elif 0 >= diff >= -2:
                for i in range(abs(diff)+1):
                    if self.default:
                        tree.append(self.default.section())
                    else:
                        tree.append(etree.Element("item"))
                
                if doSave:
                    self.save()
                    
            return tree[key]
        else:
            raise IndexError("Array access must be done with integers greater than 0")
        
    def get(self, index, xml=None):
        if xml is not None and xml is self:
            return self[index]
        else:
            if type(xml) is Xml:
                return xml[index]
            else:
                return self.getitem(index, xml)
