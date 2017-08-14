# -*- coding: utf-8 -*-

from astropy import coordinates
from astropy import units as u
from astropy.wcs import WCS
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import get_body_barycentric
from astropy.table import Table, Column

from pyraf import iraf

from datetime import datetime
from datetime import timedelta

import math
from os import path, system, getcwd
import numpy as np

import sep

from .io import FileOps
from .visuals import StarPlot


class FitsOps:

    def __init__(self, file_name):
        self.file_name = file_name
        self.timeops = TimeOps()
        self.hdu = fits.open(self.file_name, "readonly")

    def return_out_file_header(self, observer="YK", tel="TUG 100", code="A84",
                               contact="yucelkilic@myrafproject.org",
                               catalog="GAIA"):

        """
        Creates MPC report file's head.
        @param observer: Observer.
        @type observer: str
        @param tel: Telescope information.
        @type tel: str
        @param code: Observatory code.
        @type code: str
        @param contact: E-mail of the contact person.
        @type contact: str
        @param catalog: Used catalogue.
        @type catalog: str
        @return: str
        """

        head = """COD {0}
OBS {1}
MEA {2}
TEL {3} + CCD
ACK MPCReport file updated {4}
AC2 {5}
NET {6}""".format(code, observer, observer, tel,
                  self.timeops.time_stamp(),
                  contact, catalog)

        return(head)

    def get_header(self, key):

        """
        Extracts requested keyword from FITS header.

        @param key: Requested keyword.
        @type key: str
        @return: str
        """

        try:
            header_key = self.hdu[0].header[key]
            return(header_key)
        except Exception as e:
            print(e)

    def detect_sources(self, plot=False, skycoords=False, max_sources=50):

        """
        It detects sources on FITS image with sep module.
        @param plot
        @type plot: boolean
        @param skycoords: Calculate sky coordinates of sources.
        @type skycoords: boolean
        @param max_sources: Maximum detection limit.
        @type max_sources: int
        @return: astropy.table
        """

        data = self.hdu[0].data.astype(float)
        bkg = sep.Background(data)
        # bkg_image = bkg.back()
        # bkg_rms = bkg.rms()
        data_sub = data - bkg
        all_objects = sep.extract(data_sub, 1.5, err=bkg.globalrms)
        ord_objects = np.sort(all_objects, order=['flux'])

        if len(ord_objects) <= max_sources:
            max_sources = len(ord_objects)
            objects = ord_objects[::-1][:max_sources]
        if len(ord_objects) > max_sources:
            objects = ord_objects[::-1][:max_sources]
        elif not max_sources:
            objects = ord_objects[::-1]

        if plot:
            splt = StarPlot()
            splt.star_plot(data_sub, objects)

        if skycoords:
            xy2sky2_ops = AstCalc()
            objects_ra = []
            objects_dec = []
            for j in range(len(objects)):
                objects_sky = xy2sky2_ops.xy2sky2(self.file_name,
                                                  objects['x'][j],
                                                  objects['y'][j])
                objects_ra.append(objects_sky.ra.degree)
                objects_dec.append(objects_sky.dec.degree)
                
            print("{0} objects detected.".format(len(objects)))
            col_ra_calc = Table.Column(name='ra_calc', data=objects_ra)
            col_dec_calc = Table.Column(name='dec_calc', data=objects_dec)
            tobjects = Table(objects)
            tobjects.add_columns([col_ra_calc, col_dec_calc])
            return(tobjects)
        else:
            print("{0} objects detected.".format(len(objects)))
            return(Table(objects))


class AstCalc:

    def __init__(self):
        self.fileops = FileOps()
        self.timeops = TimeOps()

    def is_object(self, coor1, coor2, max_dist=10, min_dist=0):

        """
        It checks whether the object being queried is the same in the
        database within the specified limit.
        
        @param coor1: Detected object's coordinate.
        @type coor1: coordinate
        @param coor2: Calculated object's coordinate.
        @type coor2: coordinate
        @param max_dist: Max distance limit in arcsec.
        @type max_dist: integer
        @param min_dist: Max distance limit in arcsec.
        @type min_dist: int
        @return: boolean
        """

        ret = coor1.separation(coor2)
        return(min_dist <= ret.arcsecond <= max_dist)

    def flux2mag(self, flux):

        """
        Converts flux to magnitude.
        @param flux: Flux.
        @type flux: float
        @return: float
        """

        try:
            mag = 25 - 2.5 * math.log10(flux)
            return("{:.1f}".format(mag))
        except Exception as e:
            print(e)

    def find_skybot_objects(self, odate, ra, dec, radius=16,
                            observatory="A84"):

        """
        Seek and identify all the known solar system objects
        in a field of view of a given size.
        
        @param odate: Observation date.
        @type odate: date
        @param ra: RA of field center for search, format: degrees or hh:mm:ss
        @type ra: str
        @param dec: DEC of field center for search, format: degrees or hh:mm:ss
        @type dec: str
        @param radius: Radius.
        @type radius: float
        @param observatory: Observation code.
        @type observatory: str
        @return: str
        """

        try:
            epoch = self.timeops.date2jd(odate)
            bashcmd = ("wget -q \"http://vo.imcce.fr/webservices/skybot/"
                       "skybotconesearch_query.php"
                       "?-ep={0}&-ra={1}&-dec={2}&-rm={3}&-output=object&"
                       "-loc={4}&-filter=120&-objFilter=120&-from="
                       "SkybotDoc&-mime=text\" -O skybot.cat").format(
                           epoch,
                           ra,
                           dec,
                           radius,
                           observatory)

            system(bashcmd)
            skyresult = self.fileops.read_file_as_array("skybot.cat")
            system('rm -rf skybot.cat')
            return (skyresult)

        except Exception as e:
            print(e)

    def radec2wcs(self, ra, dec):

        """
        Converts string RA, DEC coordinates to astropy format.
        @param ra: RA of field center for search, format: degrees or hh:mm:ss
        @type ra: str
        @param dec: DEC of field center for search, format: degrees or hh:mm:ss
        @type dec: str
        @return: list
        """

        try:
            c = coordinates.SkyCoord('{0} {1}'.format(ra, dec),
                                     unit=(u.hourangle, u.deg), frame='icrs')

            return(c)
        except Exception as e:
            pass

    def xy2sky(self, file_name, A_x, y):

        """
        Converts physical coordinates to WCS coordinates for STDOUT.
        @param file_name: FITS image file name with path.
        @type file_name: str
        @param A_x: A_x coordinate of object.
        @type A_x: float
        @param y: y coordinate of object.
        @type y: float
        @return: str
        """

        try:
            header = fits.getheader(file_name)
            w = WCS(header)
            astcoords_deg = w.wcs_pix2world([[A_x, y]], 0)
            astcoords = coordinates.SkyCoord(astcoords_deg * u.deg,
                                             frame='icrs')
            alpha = ' '.join(astcoords.to_string(
                style='hmsdms', sep=" ", precision=2)[0].split(" ")[:3])

            delta = ' '.join(astcoords.to_string(
                style='hmsdms', sep=" ", precision=1)[0].split(" ")[3:])

            return("{0} {1}".format(alpha, delta))
        except Exception as e:
            pass

    def xy2sky2(self, file_name, A_x, y):

        """
        Converts physical coordinates to WCS coordinates for calculations.
        @param file_name: FITS image file name with path.
        @type file_name: str
        @param A_x: A_x coordinate of object.
        @type A_x: float
        @param y: y coordinate of object.
        @type y: float
        @return: list
        """

        try:
            header = fits.getheader(file_name)
            w = WCS(header)
            astcoords_deg = w.wcs_pix2world([[A_x, y]], 0)

            astcoords = coordinates.SkyCoord(
                astcoords_deg * u.deg, frame='icrs')

            return(astcoords[0])

        except Exception as e:
            pass

    def xy2skywcs(self, file_name, A_x, y):

        """
        Converts physical coordinates to WCS coordinates
        for STDOUT with wcstools' xy2sky.

        @param file_name: FITS image file name with path.
        @type file_name: str
        @param A_x: A_x coordinate of object.
        @type A_x: float
        @param y: y coordinate of object.
        @type y: float
        @return: str
        """

        try:
            file_path, file_and_ext = path.split(file_name)
            system("xy2sky {0} {1} {2} > {3}/coors".format(
                file_name,
                A_x,
                y,
                file_path))
            coors = np.genfromtxt('{0}/coors'.format(file_path),
                                  comments='#',
                                  invalid_raise=False,
                                  delimiter=None,
                                  usecols=(0, 1),
                                  dtype="U")

            system("rm -rf {0}/coors".format(file_path))

            c = coordinates.SkyCoord('{0} {1}'.format(coors[0], coors[1]),
                                     unit=(u.hourangle, u.deg), frame='fk5')

            alpha = c.to_string(style='hmsdms', sep=" ", precision=2)[:11]
            delta = c.to_string(style='hmsdms', sep=" ", precision=1)[11:]
            
            return('{0} {1}'.format(alpha, delta))
        
        except Exception as e:
            pass

    def xy2sky2wcs(self, file_name, A_x, y):

        """
        Converts physical coordinates to WCS coordinates for
        calculations with wcstools' xy2sky.
        
        @param file_name: FITS image file name with path.
        @type file_name: str
        @param A_x: A_x coordinate of object.
        @type A_x: float
        @param y: y coordinate of object.
        @type y: float
        @return: str
        """

        try:
            file_path, file_and_ext = path.split(file_name)
            system("xy2sky {0} {1} {2} > {3}/coors".format(
                file_name,
                A_x,
                y,
                file_path))
            coors = np.genfromtxt('{0}/coors'.format(file_path),
                                  comments='#',
                                  invalid_raise=False,
                                  delimiter=None,
                                  usecols=(0, 1),
                                  dtype="U")

            system("rm -rf {0}/coors".format(file_path))

            c = coordinates.SkyCoord('{0} {1}'.format(coors[0], coors[1]),
                                     unit=(u.hourangle, u.deg), frame='fk5')

            return(c)
        except Exception as e:
            pass

    def center_finder(self, file_name, wcs_ref=False):

        """
        It finds image center as WCS coordinates
        @param file_name: FITS image file name with path.
        @type file_name: str
        @return: list
        """

        try:
            fitsops = FitsOps(file_name)
            naxis1 = fitsops.get_header("naxis1")
            naxis2 = fitsops.get_header("naxis2")
            A_x, y = [float(naxis1) / 2, float(naxis2) / 2]

            if not wcs_ref:
                coor = self.xy2sky(file_name, A_x, y)

                ra = ' '.join(coor.split(" ")[:3])
                dec = ' '.join(coor.split(" ")[3:])

                return([ra, dec])
            else:
                coor = self.xy2sky2(file_name, A_x, y)

                center_ra = coor.ra
                center_dec = coor.dec
                
                return([center_ra,
                       center_dec])
        except Exception as e:
            print(e)

    def solve_field(self,
                    image_path,
                    tweak_order=2,
                    downsample=4,
                    radius=0.5,
                    ra=None,
                    dec=None):

        """
        The astrometry engine will take any image and return
        the astrometry world coordinate system (WCS).
        
        @param image_path: FITS image file name with path
        @type image_path: str
        @param tweak_order: Polynomial order of SIP WCS corrections
        @type tweak_order: integer
        @param downsample: Downsample the image by factor int before
        running source extraction
        @type downsample: integer
        @param radius: Only search in indexes within 'radius' of the
        field center given by --ra and --dec
        @type radius: str
        @param ra: RA of field center for search, format: degrees or hh:mm:ss
        @type ra: str
        @param dec: DEC of field center for search, format: degrees or hh:mm:ss
        @type dec: str
        @return: boolean
        """
    
        try:
            system(("solve-field --no-fits2fits --no-plots "
                    "--no-verify --tweak-order {0} "
                    "--downsample {1} --overwrite --radius {2} --no-tweak "
                    "--ra {3} --dec {4} {5}").format(tweak_order,
                                                     downsample,
                                                     radius,
                                                     ra.replace(" ", ":"),
                                                     dec.replace(" ", ":"),
                                                     image_path))
            # Cleaning
            root, extension = path.splitext(image_path)
            system(("rm -rf {0}-indx.png {0}-indx.xyls "
                    "{0}-ngc.png {0}-objs.png "
                    "{0}.axy {0}.corr "
                    "{0}.match {0}.rdls "
                    "{0}.solved {0}.wcs").format(root))

            if not path.exists(root + '.new'):
                print(image_path + ' cannot be solved!')
                return(False)
            else:
                print('Image has been solved!')
                return(True)
        
        except Exception as e:
            print(e)

    def std2equ(self, ra0, dec0, xx, yy):

        """
        Calculation of equatorial coordinates from
        standard coordinates used in astrographic plate measurement
        @param ra0: Right ascension of optical axis [rad]
        @type ra0: float
        @param dec0: Declination of optical axis [rad]
        @type dec0: float
        @param xx: Standard coordinate of X
        @type xx: float
        @param yy: Standard coordinate of Y
        @type yy: float
        @return: Tuple, ra, dec in [rad]
        """

        ra = ra0 + math.atan(-xx /
                             (math.cos(dec0) -
                              (yy * math.sin(dec0))))

        dec = math.asin((math.sin(dec0) + (yy * math.cos(dec0))) /
                        math.sqrt(1 + math.pow(xx, 2) +
                                  math.pow(yy, 2)))

        return(ra, dec)

    def equ2std(self, ra0, dec0, ra, dec):

        """
        Calculation of standard coordinates from equatorial coordinates
        @param ra0: Right ascension of optical axis [rad]
        @type ra0: float
        @param dec0: Declination of optical axis [rad]
        @type dec0: float
        @param ra: Right ascension [rad]
        @type ra: float
        @param dec: Declination
        @type dec: float
        @return: Tuple, xx, yy
        """
        xx = (-(math.cos(dec) * math.sin(ra - ra0)) /
              (math.cos(dec0) * math.cos(dec) * math.cos(ra - ra0) +
               math.sin(dec0) * math.sin(dec)))

        yy = (-(math.sin(dec0) * math.cos(dec) * math.cos(ra - ra0) -
                math.cos(dec0) * math.sin(dec)) /
              (math.cos(dec0) * math.cos(dec) * math.cos(ra - ra0) +
               math.sin(dec0) * math.sin(dec)))

        return(xx, yy)

    def plate_constants(self, ra_center, dec_center,
                        objects_matrix, target_xy):

        """
        Astrometric analysis of photographic plates.
        Add a data equation of form Ax=b to a least squares problem
        @param ra_center: RA coordinate of center of optical axis [rad]
        @type ra_center: float
        @param dec_center: DEC coordinate of center of optical axis [rad]
        @type dec_center: float
        @param objects_matrix: Return of the detect_sources
        function with skycoords.
        @type objects_matrix: astropy.table
        @param target_xy: Physical coordinates to be converted to Skycoord.
        @type target_xy: list
        @return: astropy.table
        """
        x_xy = []
        b_xx = []
        b_yy = []
        
        ra0 = ra_center
        dec0 = dec_center

        for m_object in objects_matrix:
            ra = math.radians(m_object[3])
            dec = math.radians(m_object[4])
            x_xy.append([m_object[1], m_object[2], 1])
            b_xx.append(self.equ2std(ra0, dec0, ra, dec)[0])
            b_yy.append(self.equ2std(ra0, dec0, ra, dec)[1])

        A_x = np.linalg.lstsq(np.array(x_xy), np.asarray(b_xx))[0]
        A_y = np.linalg.lstsq(np.array(x_xy), np.asarray(b_yy))[0]

        a, b, c = A_x
        d, e, f = A_y

        coor_list = []

        for s_object in objects_matrix:
            xx = a * s_object[1] + b * s_object[2] + c
            yy = f * s_object[1] + e * s_object[2] + f

            ra, dec = self.std2equ(ra0, dec0, xx, yy)
 
            d_ra = ((ra - math.radians(s_object[3])) *
                    math.cos(math.radians(s_object[4])))
            d_dec = (dec - math.radians(s_object[4]))

            delta = 3600.0 * math.sqrt(math.pow(d_ra, 2) +
                                       math.pow(d_dec, 2))

            coor_list.append([s_object[0],
                              s_object[1],
                              s_object[2],
                              s_object[3],
                              s_object[4],
                              math.degrees(ra),
                              math.degrees(dec),
                              math.degrees(d_ra) * 3600.0,
                              math.degrees(d_dec) * 3600.0,
                              delta,
                              (s_object[3] - math.degrees(ra)),
                              (s_object[4] - math.degrees(dec))])

        for i, xy in enumerate(target_xy):
            xx = a * xy[0] + b * xy[1] + c
            yy = f * xy[0] + e * xy[1] + f

            ra, dec = self.std2equ(ra0, dec0, xx, yy)

            coor_list.append([i,
                              xy[0],
                              xy[1],
                              None,
                              None,
                              math.degrees(ra),
                              math.degrees(dec),
                              None,
                              None,
                              None,
                              None,
                              None])

        results = np.array(coor_list, dtype=np.float)
        # results = results[np.isnan(results)] = 0
        
        rms_ra = np.sqrt(np.mean(np.power(results[:, 7], 2)))
        rms_dec = np.sqrt(np.mean(np.power(results[:, 8], 2)))
        rms_delta = np.sqrt(np.mean(np.power(results[:, 9], 2)))

        tb_results = Table(results, names=('id',
                                           'x',
                                           'y',
                                           'ra',
                                           'dec',
                                           'c_ra',
                                           'c_dec',
                                           'e_c_ra',
                                           'e_c_dec',
                                           'error',
                                           'diff_ra',
                                           'diff_dec'))

        return(tb_results,
               rms_ra,
               rms_dec,
               rms_delta)

    def ccmap(self, objects_matrix, image_path,
              ppm_parallax_cor=True,
              stdout=False):

        """
        Compute plate solutions using
        matched pixel and celestial coordinate lists.
        @param objects_matrix: Return of the match_catalog function
        in catalog module.
        @type objects_matrix: astropy.table
        @param image_path: FITS image without WCS keywords.
        @type image_path: path
        @param ppm_parallax_cor: Apply proper motion
        and stellar parallax correction?
        @type ppm_parallax_cor: boolean
        @param stdout: Print result as a STDOUT?
        @type stdout: boolean
        @return: boolean, FITS image with WCS solutions
        """

        remove_nan = objects_matrix['x',
                                    'y',
                                    'ra',
                                    'dec',
                                    'plx',
                                    'pmra',
                                    'pmdec']

        remove_nan = Table(remove_nan, masked=True)
        for col in remove_nan.columns.values():
            col.mask = np.isnan(col)
            col.fill_value = 0.0

        trimmed_om = remove_nan.filled()
        
        del objects_matrix
        del remove_nan

        if ppm_parallax_cor:
            corrected_coords = []
            fo = FitsOps(image_path)
            odate = fo.get_header("date-obs")

            for i in range(len(trimmed_om)):
                ra_plx, dec_plx = self.stellar_parallax_cor(
                    (trimmed_om['plx'][i] / 1000),
                    trimmed_om['ra'][i],
                    trimmed_om['dec'][i],
                    odate)

                cra_ppm, cdec_ppm = self.ppm_cor(trimmed_om['ra'][i],
                                                 trimmed_om['dec'][i],
                                                 trimmed_om['pmra'][i],
                                                 trimmed_om['pmdec'][i],
                                                 odate)

                cra = cra_ppm + (ra_plx.value / 3600)
                cdec = cdec_ppm + (dec_plx.value / 3600)

                corrected_coords.append([cra, cdec])

            cra_cdec = Table(np.array(corrected_coords),
                             names=("cra",
                                    "cdec"))

            c = coordinates.SkyCoord(cra_cdec['cra'] * u.deg,
                                     cra_cdec['cdec'] * u.deg, frame='icrs')

        else:
            c = coordinates.SkyCoord(trimmed_om['ra'] * u.deg,
                                     trimmed_om['dec'] * u.deg, frame='icrs')

        rd = c.to_string('hmsdms', sep=":", precision=5)
        radec = np.reshape(rd, (-1, 1))

        iraf.digiphot(_doprint=0)
        iraf.daophot(_doprint=0)

        ra_dec = Column(name='ra_dec', data=radec[:, 0])
        x_y = Table(trimmed_om['x', 'y'])

        x_y.add_column(ra_dec, 0)
        np.savetxt("{0}/coords".format(getcwd()), x_y, fmt='%s')

        # InputCooList should have the following columns
        SolutionsList = "{0}/solutions.txt".format(getcwd())

        iraf.ccmap.setParam('images', image_path)
        iraf.ccmap.setParam('input', "{0}/coords".format(getcwd()))
        iraf.ccmap.setParam('database', SolutionsList)
        iraf.ccmap.setParam('lngcolumn', 1)
        iraf.ccmap.setParam('latcolumn', 2)
        iraf.ccmap.setParam('xcolumn', 3)
        iraf.ccmap.setParam('ycolumn', 4)
        iraf.ccmap.setParam('results', "{0}/results".format(getcwd()))
        iraf.ccmap.setParam('refsystem', 2015.0)
        iraf.ccmap.setParam('insystem', 'icrs')
        iraf.ccmap.setParam('update', 'yes')
        iraf.ccmap(interactive='no')

        system("rm -rf {0}/coords".format(getcwd()))

        return_list = []
        
        with open("{0}/results".format(getcwd())) as f:

            for line in f:
                if "Ra/Dec or Long/Lat fit rms:" in line:
                    rms_ra_dec = line.split()
                    rms_ra = rms_ra_dec[6]
                    rms_dec = rms_ra_dec[7]
                    return_list.append([rms_ra,
                                        rms_dec,
                                        "(arcsec  arcsec)"])

                if "(hours  degrees)" in line:
                    ref_point = line.split()
                    ref_point_ra = ref_point[3]
                    ref_point_dec = ref_point[4]
                    return_list.append([ref_point_ra,
                                        ref_point_dec,
                                        "(hours  degrees)"])
                if "(pixels  pixels)" in line:
                    ref_point = line.split()
                    ref_point_x = ref_point[3]
                    ref_point_y = ref_point[4]
                    return_list.append([ref_point_x,
                                        ref_point_y,
                                        "(pixels  pixels)"])
                if "X and Y scale:" in line:
                    pix_scale = line.split()
                    pix_scale_x = pix_scale[5]
                    pix_scale_y = pix_scale[6]
                    return_list.append([pix_scale_x,
                                        pix_scale_y,
                                        "(arcsec/pixel  arcsec/pixel)"])
                if "X and Y axis rotation:" in line:
                    axis_rotation = line.split()
                    axis_rotation_x = axis_rotation[6]
                    axis_rotation_y = axis_rotation[7]
                    return_list.append([axis_rotation_x,
                                        axis_rotation_y,
                                        "(degrees  degrees)"])
                if "Ra/Dec or Long/Lat wcs rms:" in line:
                    rms_ra_dec_wcs = line.split()
                    rms_ra_wcs = rms_ra_dec_wcs[6]
                    rms_dec_wcs = rms_ra_dec_wcs[7]
                    return_list.append([rms_ra_wcs,
                                        rms_dec_wcs,
                                        "(arcsec  arcsec)"])
        f.close()

        ccmap_result = Table(return_list,
                             names=("Ra/Dec or Long/Lat fit rms",
                                    "Reference point (RA, DEC)",
                                    "Reference point (X, Y)",
                                    "X and Y scale",
                                    "X and Y axis rotation",
                                    "Ra/Dec or Long/Lat wcs rms"))

        if stdout:
            with open("{0}/results".format(getcwd())) as f:
                results = f.read()
                print(results)
            f.close()

        return(ccmap_result["Ra/Dec or Long/Lat fit rms",
                            "Ra/Dec or Long/Lat wcs rms",
                            "Reference point (RA, DEC)",
                            "Reference point (X, Y)",
                            "X and Y scale",
                            "X and Y axis rotation"])

    def ppm_cor(self, ra, dec, pmRA, pmDE, odate):
        """
        Compute stellar parallax corrections with given parameters.
        @param ra: RA coordinate of object (in degrees).
        @type ra: float
        @param dec: DEC coordinate of object (in degrees).
        @type dec: float
        @param pmRA: Proper motion in right ascension µ_α* of
        the source in ICRS at the reference epoch Epoch.
        This is the projection of the proper motion vector
        in the direction of increasing right ascension (in milliarcsec)
        @type pmRA: float
        @param pmDE: Proper motion in declination direction (in milliarcsec)
        @type pmDE: float
        @param odate: Observation time of the frame.
        @type odate: date
        @return: list
        """

        ra = math.radians(ra)
        dec = math.radians(dec)

        mu_ra = math.radians(pmRA / 3600000) / math.cos(dec)

        to = TimeOps()
        t0 = to.date2mjd("2015-01-01 00:00:00.000000")
        t = to.date2mjd(odate)

        cra = ra + ((t - t0) / 365.2568983) * mu_ra
        cdec = dec + ((t - t0) / 365.2568983) * math.radians(pmDE / 3600000)

        return(math.degrees(cra),
               math.degrees(cdec))
    
    def stellar_parallax_cor(self, parallax, ra, dec, odate):
        """
        Compute stellar parallax corrections with given parameters.
        @param parallax: Parallax value in gaia catalogue in (arcsec)
        @type parallax: float
        @param ra: RA coordinate of object (in degrees).
        @type ra: float
        @param dec: DEC coordinate of object (in degrees).
        @type dec: float
        @param odate: Observation time of the frame.
        @type odate: date
        @return: list
        """

        ra = math.radians(ra)
        dec = math.radians(dec)

        t = Time(odate)
        xyz = get_body_barycentric('earth', t, ephemeris='de432s')
        
        x = xyz.x.to(u.parsec)
        y = xyz.y.to(u.parsec)
        z = xyz.z.to(u.parsec)

        delta_ra = (parallax * (x * math.sin(ra) -
                                y * math.cos(ra))) / math.cos(dec)

        delta_dec = parallax * ((x * math.cos(ra) + y * math.sin(ra)) *
                                math.sin(dec) - z * math.cos(dec))

        return((delta_ra.value * u.rad).to(u.arcsec),
               (delta_dec.value * u.rad).to(u.arcsec))


class TimeOps:

    def time_stamp(self):

        """
        Returns time stamp as %Y-%m-%IT%H:%M:%S format.
        @return: str
        """

        return str(datetime.utcnow().strftime("%Y-%m-%IT%H:%M:%S"))

    def get_timestamp(self, dt, frmt="%Y-%m-%dT%H:%M:%S.%f"):

        """
        Returns time stamp as %Y-%m-%IT%H:%M:%S format.
        @param dt: Input date
        @type dt: date
        @param frmt: Date format
        @type frmt: str
        @return: date
        """

        try:
            if len(dt) == 19:
                frmt = "%Y-%m-%dT%H:%M:%S"
            
            t = datetime.strptime(dt, frmt)
            return(t)
        except Exception as e:
            print(e)

    def get_timestamp_exp(self, file_name, dt="date-obs", exp="exptime"):

        """
        Returns FITS file's date with exposure time included.
        @param file_name: FITS image file name with path
        @type file_name: str
        @param dt: DATE-OBS keyword
        @type dt: str
        @param exp: Exposure time keyword
        @type exp: str
        @return: date
        """

        fitsops = FitsOps(file_name)
        expt = fitsops.get_header(exp)
        dat = fitsops.get_header(dt)
        tmstamp = self.get_timestamp(dat)
        ret = tmstamp + timedelta(seconds=float(expt) / 2)

        return(ret)

    def date2jd(self, dt):

        """
        Converts date to Julian Date.
        @param dt: Date
        @type dt: str
        @return: float
        """
        
        date_t = dt
        
        if "T" not in dt:
            date_t = str(dt).replace(" ", "T")

        t_jd = Time(date_t, format='isot', scale='utc')

        return(t_jd.jd)

    def date2mjd(self, dt):

        """
        Converts date to Modified Julian Date.
        @param dt: Date
        @type dt: str
        @return: float
        """

        # 2015-03-08 23:10:01.890000

        date_t = dt
        
        if "T" not in dt:
            date_t = str(dt).replace(" ", "T")

        t_mjd = Time(date_t, format='isot', scale='utc')

        return(t_mjd.mjd)
    
    def convert_time_format(self, timestamp):

        """
        Converts date to MPC date format in MPC report file.
        @param timestamp: Date
        @type timestamp: date
        @return: str
        """

        try:
            y = timestamp.year
            m = timestamp.month
            d = timestamp.day

            h = timestamp.hour
            M = timestamp.minute
            s = timestamp.second

            cday = d + float(h) / 24 + float(M) / 1440 + float(s) / 86400

            if d >= 10:
                ret = "C{} {:02.0f} {:.5f}".format(y, float(m), float(cday))
            else:
                ret = "C{} {:02.0f} 0{:.5f}".format(y, float(m), float(cday))

            return(ret)

        except Exception as e:
            print(e)
